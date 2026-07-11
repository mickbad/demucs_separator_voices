#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
demucs_separator.py

Sépare un fichier audio en deux stems (voix / instruments) à l'aide de Demucs,
et produit deux fichiers MP3 :
    <nom>-voices.mp3
    <nom>-instruments.mp3

Si le fichier source est un MP3, les tags ID3 (titre, artiste, pochette, etc.)
sont recopiés dans les deux fichiers de sortie.

Usage:
    demucs_separator [-h] [--version] fichier

Sorties (une ligne JSON à la fois, sur stdout) :
    En cours de traitement :
        {"running": true, "eta": <secondes|null>, "progres": <0-100|null>}
    En fin de traitement (succès) :
        {"running": false, "voice": "/chemin/vers/fichier-voices.mp3",
         "intruments": "/chemin/vers/fichier-instruments.mp3", "err": ""}
    En cas d'erreur :
        {"running": false, "err": "message d'erreur"}
"""

import sys
import os
import re
import json
import shutil
import argparse
import platform
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
from datetime import timedelta

__version__ = "1.0.0"


# --------------------------------------------------------------------------
# Certificats SSL (nécessaire pour torch.hub / urllib dans un exécutable
# PyInstaller isolé, où OpenSSL ne trouve pas forcément le magasin de
# certificats CA du système sur la machine cible).
# --------------------------------------------------------------------------

def _setup_ssl_certs():
    try:
        import certifi
        cert_path = certifi.where()
        os.environ.setdefault("SSL_CERT_FILE", cert_path)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", cert_path)
    except Exception:
        # Si certifi est absent pour une raison quelconque, on laisse
        # OpenSSL utiliser son comportement par défaut (ne bloque pas
        # le démarrage du programme).
        pass


_setup_ssl_certs()


# --------------------------------------------------------------------------
# Sortie JSON
# --------------------------------------------------------------------------

def emit(payload: dict):
    """Écrit une ligne JSON sur stdout (une ligne = un événement)."""
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def emit_progress(progress: Optional[float], eta: Optional[int]):
    eta_human = timedelta(seconds=eta) if eta is not None else None
    emit({"running": True, "eta": eta, "eta_human": str(eta_human) if eta_human else None, "progress": progress})


def emit_success(voice_path: str, instruments_path: str):
    emit({"running": False, "voice": voice_path, "intruments": instruments_path, "err": None})


def emit_error(message: str):
    emit({"running": False, "err": message})


# --------------------------------------------------------------------------
# Localisation de ffmpeg : d'abord le répertoire d'exécution, puis le PATH
# --------------------------------------------------------------------------

def get_base_dir() -> Path:
    """
    Répertoire d'exécution du programme :
      - si le programme est un exécutable compilé (PyInstaller), le dossier
        contenant l'exécutable ;
      - sinon, le dossier contenant le script demucs_separator.py.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(os.path.abspath(sys.argv[0])).resolve().parent


def find_ffmpeg() -> Optional[str]:
    """
    Cherche ffmpeg :
      1. dans le répertoire d'exécution du programme,
      2. puis dans le PATH.
    Retourne le chemin complet vers l'exécutable, ou None si introuvable.
    """
    exe_name = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"

    local_candidate = get_base_dir() / exe_name
    if local_candidate.is_file() and os.access(local_candidate, os.X_OK):
        return str(local_candidate)

    found_in_path = shutil.which("ffmpeg")
    if found_in_path:
        return found_in_path

    return None


# --------------------------------------------------------------------------
# Interception de la progression Demucs (barre tqdm) -> JSON
# --------------------------------------------------------------------------

class DemucsProgressCapture:
    """
    Flux de substitution pour stderr qui intercepte la barre de progression
    tqdm émise par Demucs et déclenche emit_progress() à chaque mise à jour.
    """

    # Ex: " 87%|████████▋ | 87/100 [00:12<00:01,  7.14it/s]"
    TQDM_RE = re.compile(
        r"(?P<percent>\d{1,3})%\|.*?\[(?P<elapsed>[\d:]+)<(?P<remaining>[\d:]+)"
    )

    def __init__(self, progress_range=(0, 90)):
        self._buffer = ""
        self._range_start, self._range_end = progress_range

    @staticmethod
    def _to_seconds(hms: str) -> Optional[int]:
        parts = hms.split(":")
        try:
            parts_i = [int(p) for p in parts]
        except ValueError:
            return None
        seconds = 0
        for p in parts_i:
            seconds = seconds * 60 + p
        return seconds

    def write(self, text: str):
        self._buffer += text
        # tqdm réécrit la ligne en cours avec des '\r'
        while True:
            r_idx = self._buffer.find("\r")
            n_idx = self._buffer.find("\n")
            candidates = [i for i in (r_idx, n_idx) if i != -1]
            if not candidates:
                break
            sep_idx = min(candidates)
            chunk, self._buffer = self._buffer[:sep_idx], self._buffer[sep_idx + 1:]
            self._process_chunk(chunk)

    def _process_chunk(self, chunk: str):
        match = self.TQDM_RE.search(chunk)
        if not match:
            return
        percent = int(match.group("percent"))
        eta = self._to_seconds(match.group("remaining"))
        mapped = self._range_start + (percent / 100.0) * (self._range_end - self._range_start)
        emit_progress(round(mapped, 1), eta)

    def flush(self):
        pass


# --------------------------------------------------------------------------
# Séparation Demucs
# --------------------------------------------------------------------------

def run_demucs(input_path: Path, work_dir: Path, model: str = "htdemucs") -> Path:
    """
    Lance Demucs en mode "two-stems" (vocals / no_vocals) sur le fichier donné.
    Retourne le dossier contenant vocals.wav et no_vocals.wav.
    """
    from demucs import separate as demucs_separate

    args = [
        "-n", model,
        "--two-stems", "vocals",
        "-o", str(work_dir),
        str(input_path),
    ]

    real_stderr = sys.stderr
    sys.stderr = DemucsProgressCapture(progress_range=(0, 90))
    try:
        try:
            demucs_separate.main(args)
        except SystemExit as e:
            if e.code not in (0, None):
                raise RuntimeError(f"Demucs a échoué (code de sortie {e.code})")
        except (ImportError, ModuleNotFoundError) as e:
            if "torchcodec" in str(e).lower():
                raise RuntimeError(
                    "Cette version de torchaudio nécessite le paquet 'torchcodec'. "
                    "Celui-ci est absent de l'exécutable ou de l'environnement Python."
                ) from e
            raise
    finally:
        sys.stderr = real_stderr

    track_name = input_path.stem
    stems_dir = work_dir / model / track_name

    if not stems_dir.exists():
        raise RuntimeError(f"Dossier de sortie Demucs introuvable : {stems_dir}")

    return stems_dir


# --------------------------------------------------------------------------
# Conversion audio
# --------------------------------------------------------------------------

def get_audio_duration_seconds(ffmpeg_bin: str, media_path: Path) -> Optional[float]:
    """
    Détermine la durée (en secondes) d'un fichier audio en interrogeant ffmpeg
    (ligne "Duration: HH:MM:SS.xx" affichée sur stderr). Retourne None si la
    durée n'a pas pu être déterminée.
    """
    cmd = [ffmpeg_bin, "-i", str(media_path)]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stderr_text = result.stderr.decode(errors="ignore")

    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", stderr_text)
    if not match:
        return None

    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def convert_to_mp3(
    ffmpeg_bin: str,
    wav_path: Path,
    mp3_path: Path,
    bitrate: str = "320k",
    progress_range: Optional[tuple] = None,
):
    """
    Convertit un fichier WAV en MP3 via ffmpeg.

    Si progress_range=(start, end) est fourni, la progression réelle de
    l'encodage ffmpeg est suivie (via `-progress pipe:1`) et mappée
    linéairement dans cette plage, avec des appels successifs à
    emit_progress().
    """
    duration_seconds = None
    if progress_range is not None:
        duration_seconds = get_audio_duration_seconds(ffmpeg_bin, wav_path)

    cmd = [
        ffmpeg_bin, "-y",
        "-i", str(wav_path),
        "-codec:a", "libmp3lame",
        "-b:a", bitrate,
        "-progress", "pipe:1",
        "-nostats",
        "-loglevel", "error",
        str(mp3_path),
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    if progress_range is not None and duration_seconds:
        range_start, range_end = progress_range
        for line in proc.stdout:
            line = line.strip()
            if line.startswith("out_time_ms="):
                try:
                    out_time_ms = int(line.split("=", 1)[1])
                except ValueError:
                    continue
                current_seconds = out_time_ms / 1_000_000
                progress = min(100.0, max(0.0, (current_seconds / duration_seconds) * 100.0))
                mapped_progress = range_start + (progress / 100.0) * (range_end - range_start)
                emit_progress(round(mapped_progress, 1), None)
            elif line == "progress=end":
                emit_progress(range_end, None)
    else:
        # Pas de plage de progression demandée, ou durée introuvable :
        # on laisse simplement ffmpeg tourner jusqu'au bout.
        if proc.stdout is not None:
            proc.stdout.read()

    stderr_output = proc.stderr.read() if proc.stderr is not None else ""
    return_code = proc.wait()

    if return_code != 0:
        raise RuntimeError(
            f"Échec de la conversion ffmpeg pour {wav_path.name} : "
            f"{stderr_output.strip()}"
        )


# --------------------------------------------------------------------------
# Tags ID3
# --------------------------------------------------------------------------

def copy_id3_tags(source_mp3: Path, target_mp3: Path):
    """
    Copie l'intégralité des frames ID3 (titre, artiste, album, pochette APIC, etc.)
    du fichier source vers le fichier cible.
    """
    from mutagen.id3 import ID3, ID3NoHeaderError

    try:
        src_tags = ID3(str(source_mp3))
    except ID3NoHeaderError:
        return  # Pas de tags à copier

    try:
        dst_tags = ID3(str(target_mp3))
    except ID3NoHeaderError:
        dst_tags = ID3()

    for frame in src_tags.values():
        dst_tags.add(frame)

    dst_tags.save(str(target_mp3), v2_version=3)


# --------------------------------------------------------------------------
# Programme principal
# --------------------------------------------------------------------------

def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="demucs_separator",
        description="Sépare un fichier audio en stems voix/instruments via Demucs.",
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version=f"{__version__}",
        # version=f"%(prog)s {__version__}",
        help="afficher la version du logiciel et quitter",
    )

    parser.add_argument(
        "fichier",
        help="chemin du fichier audio à traiter",
    )
    return parser.parse_args(argv)


def process(input_arg: str, ffmpeg_bin: str):
    input_path = Path(input_arg).expanduser().resolve()

    if not input_path.is_file():
        raise FileNotFoundError(f"fichier introuvable : {input_path}")

    output_dir = input_path.parent
    base_name = input_path.stem
    is_mp3_source = input_path.suffix.lower() == ".mp3"

    voices_out = output_dir / f"{base_name}-voices.mp3"
    instruments_out = output_dir / f"{base_name}-instruments.mp3"

    emit_progress(0, None)

    work_dir = Path(tempfile.mkdtemp(prefix="demucs_"))
    try:
        stems_dir = run_demucs(input_path, work_dir)

        vocals_wav = stems_dir / "vocals.wav"
        instruments_wav = stems_dir / "no_vocals.wav"

        if not vocals_wav.exists() or not instruments_wav.exists():
            raise RuntimeError("fichiers de stems introuvables après séparation Demucs")

        convert_to_mp3(ffmpeg_bin, vocals_wav, voices_out, progress_range=(90, 95))
        convert_to_mp3(ffmpeg_bin, instruments_wav, instruments_out, progress_range=(95, 99))

        emit_progress(99, None)
        if is_mp3_source:
            copy_id3_tags(input_path, voices_out)
            copy_id3_tags(input_path, instruments_out)
    finally:
        # Nettoyage systématique des fichiers temporaires Demucs,
        # même en cas d'erreur.
        shutil.rmtree(work_dir, ignore_errors=True)

    return str(voices_out), str(instruments_out)


def main():
    args = parse_args(sys.argv[1:])

    try:
        ffmpeg_bin = find_ffmpeg()
        if ffmpeg_bin is None:
            raise RuntimeError(
                "ffmpeg introuvable (ni dans le répertoire d'exécution, ni dans le PATH)"
            )

        voices_out, instruments_out = process(args.fichier, ffmpeg_bin)
        emit_success(voices_out, instruments_out)

    except Exception as e:
        emit_error(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
