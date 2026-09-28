"""Transporte HTTP; nunca reintentar una escritura con un ID nuevo."""
from urllib.parse import urlparse
import requests


class ServiceUnavailable(RuntimeError):
    pass


class InventoryClient:
    def __init__(self, url, token):
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "script.google.com" or not parsed.path.endswith("/exec"):
            raise ValueError("Configura la URL /exec de la implementación de Apps Script.")
        if not isinstance(token, str) or len(token) < 32:
            raise ValueError("El token del servicio debe tener al menos 32 caracteres.")
        self.url, self.token = url, token

    def execute(self, command):
        try:
            response = requests.post(self.url, json={**command, "token": self.token}, timeout=(10, 70))
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
                raise ValueError("Respuesta inesperada del servicio")
            return result
        except (requests.RequestException, ValueError) as exc:
            # No incluir cuerpo, token, URL privada ni credenciales en el mensaje.
            raise ServiceUnavailable("el servicio no devolvió una confirmación válida") from exc

    def snapshot(self, user):
        result = self.execute({"action": "snapshot", "user": user})
        if not result["ok"]:
            raise ServiceUnavailable(result.get("message", "No se pudieron leer los datos"))
        return result["data"]
