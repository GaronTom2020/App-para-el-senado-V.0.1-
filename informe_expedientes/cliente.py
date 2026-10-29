"""Acceso al sitio del Senado: reintentos, ritmo de pedidos, caché y cancelación."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import config


class Cancelado(Exception):
    """El usuario canceló la operación."""


class ErrorRed(Exception):
    """El sitio no respondió o respondió con error."""


@dataclass
class Respuesta:
    url: str
    estado: int
    texto: str = ""
    contenido: bytes | None = None
    desde_cache: bool = False


class Cliente:
    def __init__(
        self,
        carpeta_cache: Path | None = None,
        usar_cache: bool = True,
        intervalo: float = config.INTERVALO_ENTRE_PEDIDOS,
        timeout: tuple[float, float] = (10, 45),
        cancelar: threading.Event | None = None,
        carpeta_diagnostico: Path | None = None,
    ):
        self.carpeta_cache = Path(carpeta_cache) if carpeta_cache else None
        self.usar_cache = usar_cache and self.carpeta_cache is not None
        self.intervalo = intervalo
        self.timeout = timeout
        self.cancelar = cancelar
        self.carpeta_diagnostico = Path(carpeta_diagnostico) if carpeta_diagnostico else None
        self._local = threading.local()
        self._turno = threading.Lock()
        self._contador = threading.Lock()
        self._ultimo = 0.0
        self.pedidos_red = 0
        self.pedidos_cache = 0
        if self.usar_cache:
            self.carpeta_cache.mkdir(parents=True, exist_ok=True)
        if self.carpeta_diagnostico:
            self.carpeta_diagnostico.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ sesión

    def _sesion(self) -> requests.Session:
        sesion = getattr(self._local, "sesion", None)
        if sesion is None:
            sesion = requests.Session()
            sesion.headers.update({
                "User-Agent": config.USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "es-AR,es;q=0.9",
            })
            reintentos = Retry(
                total=3, connect=3, read=2, backoff_factor=0.8,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=frozenset(["GET", "POST"]),
                raise_on_status=False,
            )
            adaptador = HTTPAdapter(max_retries=reintentos, pool_maxsize=8)
            sesion.mount("https://", adaptador)
            sesion.mount("http://", adaptador)
            self._local.sesion = sesion
        return sesion

    def sesion_nueva(self) -> None:
        """Descarta cookies (el buscador usa un token por sesión)."""
        self._local.sesion = None

    def verificar_cancelacion(self) -> None:
        if self.cancelar is not None and self.cancelar.is_set():
            raise Cancelado()

    def _esperar_turno(self) -> None:
        # Espaciado entre inicios de pedidos para no sobrecargar el sitio.
        with self._turno:
            espera = self._ultimo + self.intervalo - time.monotonic()
            if espera > 0:
                time.sleep(espera)
            self._ultimo = time.monotonic()

    # ---------------------------------------------------------------- pedidos

    def get(self, url: str, ttl: float | None = None, binario: bool = False) -> Respuesta:
        self.verificar_cancelacion()
        if ttl and self.usar_cache and not binario:
            guardada = self._leer_cache(url, ttl)
            if guardada is not None:
                with self._contador:
                    self.pedidos_cache += 1
                return guardada
        self._esperar_turno()
        self.verificar_cancelacion()
        try:
            resp = self._sesion().get(url, timeout=self.timeout)
        except requests.RequestException as e:
            raise ErrorRed(f"No se pudo conectar con {url} ({type(e).__name__}).") from e
        return self._procesar(url, resp, ttl, binario)

    def post(self, url: str, datos: dict) -> Respuesta:
        self.verificar_cancelacion()
        self._esperar_turno()
        try:
            resp = self._sesion().post(url, data=datos, timeout=self.timeout)
        except requests.RequestException as e:
            raise ErrorRed(f"No se pudo conectar con {url} ({type(e).__name__}).") from e
        return self._procesar(url, resp, None, False)

    def _procesar(self, url: str, resp: requests.Response, ttl, binario: bool) -> Respuesta:
        with self._contador:
            self.pedidos_red += 1
        if resp.status_code >= 400:
            raise ErrorRed(f"El sitio respondió con el código {resp.status_code} para {url}.")
        if binario:
            return Respuesta(resp.url, resp.status_code, contenido=resp.content)
        tipo = resp.headers.get("Content-Type", "").lower()
        if not resp.encoding or ("charset" not in tipo and resp.encoding.lower() == "iso-8859-1"):
            resp.encoding = resp.apparent_encoding or "utf-8"
        r = Respuesta(resp.url, resp.status_code, resp.text)
        if ttl and self.usar_cache:
            self._guardar_cache(url, r)
        self._diagnostico(url, r)
        return r

    # ------------------------------------------------------------------ caché

    def _archivo_cache(self, url: str) -> Path:
        return self.carpeta_cache / (hashlib.sha1(url.encode("utf-8")).hexdigest() + ".json")

    def _leer_cache(self, url: str, ttl: float) -> Respuesta | None:
        archivo = self._archivo_cache(url)
        try:
            datos = json.loads(archivo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if time.time() - datos.get("guardado", 0) > ttl:
            return None
        return Respuesta(datos.get("final", url), datos.get("estado", 200), datos.get("texto", ""), desde_cache=True)

    def _guardar_cache(self, url: str, r: Respuesta) -> None:
        archivo = self._archivo_cache(url)
        temporal = archivo.with_suffix(f".{threading.get_ident()}.tmp")
        try:
            temporal.write_text(
                json.dumps({"url": url, "final": r.url, "estado": r.estado, "guardado": time.time(), "texto": r.texto}),
                encoding="utf-8",
            )
            os.replace(temporal, archivo)
        except OSError:
            pass

    def vaciar_cache(self) -> int:
        if not self.carpeta_cache or not self.carpeta_cache.exists():
            return 0
        borrados = 0
        for archivo in self.carpeta_cache.glob("*.json"):
            try:
                archivo.unlink()
                borrados += 1
            except OSError:
                pass
        return borrados

    def _diagnostico(self, url: str, r: Respuesta) -> None:
        if not self.carpeta_diagnostico:
            return
        nombre = re.sub(r"[^A-Za-z0-9]+", "_", url.split("//", 1)[-1])[-120:]
        try:
            (self.carpeta_diagnostico / f"{int(time.time() * 1000)}_{nombre}.html").write_text(r.texto, encoding="utf-8")
        except OSError:
            pass
