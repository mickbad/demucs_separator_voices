#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
demucs_separator.py

Sépare un fichier audio en 2, 4 ou 6 stems à l'aide de Demucs, et produit
un fichier MP3 par stem, nommé <nom>-<stem>.mp3, à côté du fichier source.

Nombre de stems (--stems, défaut 2) :
    2 : voix / instruments                              (modèle htdemucs, mode two-stems)
    4 : voix / percussions / instruments                (modèle htdemucs, séparation complète)
    6 : voix / percussions / basse / guitare / piano / instruments (le reste)
        (modèle htdemucs_6s, séparation complète)

Le modèle Demucs correspondant (htdemucs ou htdemucs_6s) est téléchargé
automatiquement par la librairie demucs lors du tout premier usage de ce
modèle (mis en cache localement ensuite, voir README.md).

Dispositif de calcul (--device, défaut auto) : auto (choisit automatiquement
le meilleur dispositif disponible sur la machine, dans l'ordre de préférence
cuda > mps > cpu), ou cpu/cuda/mps explicite. Si le dispositif demandé
explicitement n'est pas disponible sur la machine, le programme replie
automatiquement sur cpu (message envoyé sur stderr, sans jamais polluer le
flux JSON de stdout).

Si le fichier source est un MP3, les tags ID3 (titre, artiste, pochette,
etc.) sont recopiés dans tous les fichiers de sortie générés.

Usage:
    demucs_separator [-h] [--version] [--stems {2,4,6}] [--device {cpu,cuda,mps}] fichier

Sorties (une ligne JSON à la fois, sur stdout) :
    En cours de traitement :
        {"running": true, "eta": <secondes|null>, "progress": <0-100|null>}
    En fin de traitement (succès), les clés présentes dépendent de --stems :
        --stems 2 (comportement historique, inchangé) :
            {"running": false, "voice": "...", "intruments": "...", "err": null}
        --stems 4 (ajoute "percussions") :
            {"running": false, "voice": "...", "percussions": "...", "intruments": "...", "err": null}
        --stems 6 (ajoute "percussions", "basse", "guitare", "piano") :
            {"running": false, "voice": "...", "percussions": "...", "basse": "...",
             "guitare": "...", "piano": "...", "intruments": "...", "err": null}
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
from typing import Optional, Dict, List
from datetime import timedelta

__version__ = "2.0.0"


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


def _setup_mps_fallback():
    """
    Certaines opérations de Demucs (dans la partie "transformer hybride" du
    modèle htdemucs) ne sont pas supportées nativement par le backend MPS
    de PyTorch sur Apple Silicon, ce qui provoque une erreur du type :

        Output channels > 65536 not supported at the MPS device.

    Cette variable d'environnement autorise PyTorch à replier automatiquement
    UNIQUEMENT ces opérations précises sur le CPU, en gardant le reste du
    calcul sur le GPU MPS (plus lent pour ces opérations spécifiques, mais
    fonctionnel). Elle doit être positionnée avant tout import de torch pour
    être prise en compte de façon fiable, d'où son placement ici, tout en
    haut du fichier — que --device mps soit demandé explicitement ou choisi
    automatiquement par --device auto.
    """
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")


_setup_ssl_certs()
_setup_mps_fallback()


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


def emit_success(outputs: Dict[str, str]):
    """
    Émet la ligne JSON finale de succès.

    `outputs` est la map {clé_stem: chemin_fichier_mp3} renvoyée par process().
    Seules les clés effectivement produites (donc dépendant de --stems) sont
    incluses : avec --stems 2 on ne verra que "voice"/"intruments", avec
    --stems 4 ou 6 les clés supplémentaires ("percussions", "basse", "guitare",
    "piano") s'ajoutent naturellement puisqu'elles sont présentes dans la map.
    """
    payload = {"running": False, "err": None}
    payload.update(outputs)
    emit(payload)


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
# Résolution du dispositif de calcul (--device)
# --------------------------------------------------------------------------

def _mps_available(torch_module) -> bool:
    """Renvoie True si le backend MPS (GPU Apple Silicon) est utilisable."""
    return getattr(torch_module.backends, "mps", None) is not None and torch_module.backends.mps.is_available()


def resolve_device(device: str) -> str:
    """
    Résout le dispositif de calcul effectif à utiliser.

    - "auto" (valeur par défaut) : choisit automatiquement le meilleur
      dispositif détecté sur la machine, dans l'ordre de préférence
      cuda > mps > cpu. Aucun avertissement n'est émis dans ce cas, c'est
      le fonctionnement normal attendu.
    - "cpu"/"cuda"/"mps" explicite : utilisé tel quel si disponible, sinon
      repli automatique sur cpu.

    Les messages d'information/avertissement partent sur stderr uniquement :
    stdout doit rester strictement réservé aux lignes JSON (voir en-tête).
    """
    try:
        import torch
    except ImportError:
        # torch sera de toute façon requis par demucs plus loin ; on ne
        # bloque pas ici, l'erreur explicite remontera au moment voulu.
        return "cpu" if device == "auto" else device

    if device == "auto":
        if torch.cuda.is_available():
            chosen = "cuda"
        elif _mps_available(torch):
            chosen = "mps"
        else:
            chosen = "cpu"
        print(f"--device auto : dispositif sélectionné = {chosen}", file=sys.stderr)
        return chosen

    if device == "cuda" and not torch.cuda.is_available():
        print("GPU CUDA non détecté, repli sur cpu.", file=sys.stderr)
        return "cpu"

    if device == "mps" and not _mps_available(torch):
        print("GPU MPS (Apple Silicon) non détecté, repli sur cpu.", file=sys.stderr)
        return "cpu"

    return device


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

    def __init__(self, progress_range=(0, 70)):
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
# Plan de séparation selon --stems
# --------------------------------------------------------------------------

def get_stem_plan(stems: int):
    """
    Retourne (model, two_stems, tracks) pour le nombre de stems demandé.

    - model      : nom du modèle Demucs à utiliser.
    - two_stems  : True pour utiliser le mode rapide "--two-stems vocals"
                   de Demucs (uniquement pertinent/possible pour 2 stems).
    - tracks     : liste ordonnée de dicts décrivant chaque fichier de
                   sortie final :
                     "key"     -> clé utilisée dans le JSON de sortie
                     "suffix"  -> suffixe du fichier ("<nom>-<suffix>.mp3")
                     "sources" -> liste des fichiers wav bruts (produits par
                                  Demucs dans son dossier de stems) à sommer
                                  pour obtenir cette piste. Une seule entrée
                                  = pas de mixage, copie directe.
    """
    if stems == 2:
        model = "htdemucs"
        two_stems = True
        tracks = [
            {"key": "voice", "suffix": "voices", "sources": ["vocals.wav"]},
            {"key": "intruments", "suffix": "instruments", "sources": ["no_vocals.wav"]},
        ]
    elif stems == 4:
        model = "htdemucs"
        two_stems = False
        tracks = [
            {"key": "voice", "suffix": "voices", "sources": ["vocals.wav"]},
            {"key": "percussions", "suffix": "percussions", "sources": ["drums.wav"]},
            {"key": "intruments", "suffix": "instruments", "sources": ["bass.wav", "other.wav"]},
        ]
    else:  # 6
        model = "htdemucs_6s"
        two_stems = False
        tracks = [
            {"key": "voice", "suffix": "voices", "sources": ["vocals.wav"]},
            {"key": "percussions", "suffix": "percussions", "sources": ["drums.wav"]},
            {"key": "basse", "suffix": "basse", "sources": ["bass.wav"]},
            {"key": "guitare", "suffix": "guitare", "sources": ["guitar.wav"]},
            {"key": "piano", "suffix": "piano", "sources": ["piano.wav"]},
            {"key": "intruments", "suffix": "instruments", "sources": ["other.wav"]},
        ]
    return model, two_stems, tracks


# --------------------------------------------------------------------------
# Séparation Demucs
# --------------------------------------------------------------------------

def run_demucs(input_path: Path, work_dir: Path, model: str, two_stems: bool, device: str) -> Path:
    """
    Lance Demucs sur le fichier donné avec le modèle et le dispositif
    demandés. En mode two_stems=True, seules vocals.wav/no_vocals.wav sont
    produites (plus rapide). Sinon, Demucs produit tous les stems natifs du
    modèle (vocals/drums/bass/other, +guitar/piano pour htdemucs_6s).

    Retourne le dossier contenant les fichiers wav bruts.
    """
    from demucs import separate as demucs_separate

    args = ["-n", model, "--device", device]
    if two_stems:
        args += ["--two-stems", "vocals"]
    args += ["-o", str(work_dir), str(input_path)]

    real_stderr = sys.stderr
    sys.stderr = DemucsProgressCapture(progress_range=(0, 70))
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


def prepare_track_wav(stems_dir: Path, work_dir: Path, sources: List[str]) -> Path:
    """
    Retourne le chemin du wav à convertir en mp3 pour une piste donnée.

    - Une seule source -> renvoie directement le fichier produit par Demucs
      (pas de recopie inutile).
    - Plusieurs sources -> les additionne (mixage simple), normalise si
      écrêtage, puis écrit le résultat dans un wav temporaire du work_dir.
    """
    # importation des libs
    import numpy as np
    import soundfile as sf

    if len(sources) == 1:
        return stems_dir / sources[0]

    mixed = None
    sample_rate = None
    for src in sources:
        data, sr = sf.read(stems_dir / src)
        if sample_rate is None:
            sample_rate = sr
        elif sr != sample_rate:
            raise RuntimeError(f"Sample rates incohérents entre stems Demucs ({src})")

        data = data.astype(np.float64)
        if mixed is None:
            mixed = data
        else:
            n = min(len(mixed), len(data))
            mixed = mixed[:n] + data[:n]

    peak = float(np.max(np.abs(mixed))) if mixed.size else 0.0
    if peak > 1.0:
        mixed = mixed / peak

    merged_name = "merged_" + "_".join(Path(s).stem for s in sources) + ".wav"
    merged_path = work_dir / merged_name
    sf.write(merged_path, mixed, sample_rate)
    return merged_path


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
        description="Sépare un fichier audio en stems (2, 4 ou 6) via Demucs.",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"{__version__}",
        help="afficher la version du logiciel et quitter",
    )

    parser.add_argument(
        "--stems",
        type=int,
        choices=[2, 4, 6],
        default=2,
        help="nombre de stems à produire : 2 = voix/instruments (défaut), "
             "4 = + percussions, 6 = + basse/guitare/piano",
    )

    parser.add_argument(
        "--device",
        type=str,
        choices=["auto", "cpu", "cuda", "mps"],
        default="auto",
        help="dispositif de calcul pour Demucs : auto (défaut, choisit le meilleur "
             "dispositif disponible : cuda > mps > cpu), ou cpu/cuda/mps explicite. "
             "Repli automatique sur cpu si le dispositif demandé est indisponible.",
    )

    parser.add_argument(
        "fichier",
        help="chemin du fichier audio à traiter",
    )
    return parser.parse_args(argv)


def process(input_arg: str, ffmpeg_bin: str, stems: int, device: str) -> Dict[str, str]:
    """
    Traite le fichier d'entrée et renvoie une map {clé_stem: chemin_mp3}.

    Le contenu de cette map dépend de --stems (voir get_stem_plan) : c'est
    elle qui détermine ensuite les clés effectivement émises par
    emit_success(), sans rien coder en dur ici sur le nombre de stems.
    """
    input_path = Path(input_arg).expanduser().resolve()

    if not input_path.is_file():
        raise FileNotFoundError(f"fichier introuvable : {input_path}")

    output_dir = input_path.parent
    base_name = input_path.stem
    is_mp3_source = input_path.suffix.lower() == ".mp3"

    model, two_stems, tracks = get_stem_plan(stems)

    emit_progress(0, None)

    work_dir = Path(tempfile.mkdtemp(prefix="demucs_"))
    results: Dict[str, str] = {}
    try:
        # --- Étape 1 : séparation Demucs (sorties intermédiaires inchangées) ---
        stems_dir = run_demucs(input_path, work_dir, model, two_stems, device)

        for track in tracks:
            for src in track["sources"]:
                if not (stems_dir / src).exists():
                    raise RuntimeError(f"fichier de stem introuvable après séparation Demucs : {src}")

        # --- Étape 2 : mixage éventuel + conversion mp3, une piste à la fois ---
        # Répartition de la plage de progression restante (70 -> 99) entre
        # les pistes à produire, quel que soit leur nombre.
        n_tracks = len(tracks)
        conv_start, conv_end = 70.0, 99.0
        slice_width = (conv_end - conv_start) / n_tracks

        for i, track in enumerate(tracks):
            wav_path = prepare_track_wav(stems_dir, work_dir, track["sources"])
            out_mp3 = output_dir / f"{base_name}-{track['suffix']}.mp3"

            range_start = conv_start + i * slice_width
            range_end = range_start + slice_width
            convert_to_mp3(
                ffmpeg_bin, wav_path, out_mp3,
                progress_range=(round(range_start, 1), round(range_end, 1)),
            )
            results[track["key"]] = str(out_mp3)

        emit_progress(99, None)
        if is_mp3_source:
            for mp3_path_str in results.values():
                copy_id3_tags(input_path, Path(mp3_path_str))
    finally:
        # Nettoyage systématique des fichiers temporaires Demucs,
        # même en cas d'erreur.
        shutil.rmtree(work_dir, ignore_errors=True)

    return results


def main():
    args = parse_args(sys.argv[1:])

    try:
        ffmpeg_bin = find_ffmpeg()
        if ffmpeg_bin is None:
            raise RuntimeError(
                "ffmpeg introuvable (ni dans le répertoire d'exécution, ni dans le PATH)"
            )

        device = resolve_device(args.device)
        results = process(args.fichier, ffmpeg_bin, args.stems, device)
        emit_success(results)

    except Exception as e:
        emit_error(str(e))
        sys.exit(1)


if __name__ == "__main__":
    # Indispensable pour tout exécutable packagé (PyInstaller) qui utilise
    # multiprocessing en interne (c'est le cas de torch/Demucs, notamment
    # via le resource_tracker). Sur macOS/Windows, un processus enfant est
    # relancé en réinvoquant "l'interpréteur Python" avec des flags internes
    # (-B -S -I -c ...) ; dans un exécutable onefile, il n'y a pas de vrai
    # interpréteur à relancer, c'est le programme compilé lui-même qui se
    # relance. Sans freeze_support(), ces flags internes atterrissent dans
    # notre propre parse_args(), qui les rejette (usage: ... unrecognized
    # arguments) à chaque processus enfant relancé. freeze_support() les
    # intercepte avant que notre code ne s'exécute. Doit être appelé en tout
    # premier, avant tout autre traitement de ce bloc.
    import multiprocessing
    multiprocessing.freeze_support()

    main()
