# Goujana Agenda — Alertas de calendarios

App de escritorio (PyQt6) que corre en la bandeja del sistema para avisar de
citas próximas, permitir grabar la pantalla (llamada/reunión) y crear PQRs en
el ERP Sofisis con el resumen y la grabación adjunta.

Se empaqueta con PyInstaller y se distribuye con un instalador Inno Setup
(`build/setup.iss`) que la registra para autoarrancar con Windows.

## Modo soporte técnico (`goujanareporte://`)

Además del flujo normal (login + agenda), la app tiene un **modo soporte
técnico** minimalista, sin login, pensado para que un usuario del ERP grabe
en el momento la pantalla de un problema y lo envíe como reporte — sin tener
que abrir sesión en esta app ni conocer su configuración.

### Cómo se lanza

1. El navegador, con la sesión del ERP ya logueada, hace:
   `POST <server>/admin/crm_s/report_issue/start/` y recibe `{id, token}`.
   `token` es un string firmado de un solo propósito, válido ~2 horas, que
   autoriza terminar ESE reporte puntual sin sesión ni cookies.
2. El navegador abre el link de protocolo:
   `goujanareporte://start?token=<token>&server=<url_base_del_tenant>`
   (ejemplo: `goujanareporte://start?token=XXX&server=https://goujana.co`).
3. Windows invoca el ejecutable pasando la URL completa como `argv[1]`
   (ej. `Goujana Agenda.exe "goujanareporte://start?token=XXX&server=..."`).
   El protocolo se registra en el instalador — ver `[Registry]` en
   `build/setup.iss` (claves bajo `HKCU\Software\Classes\goujanareporte`).
4. `main.py:parse_support_launch()` detecta el argumento con ese esquema,
   extrae `token` y `server` de la query string, y en vez de abrir la agenda
   normal abre `ui/support_window.py:SupportWindow` — una ventana suelta,
   sin la UI de agenda/CRM, sin el single-instance lock de la app normal
   (puede coexistir con una instancia de agenda ya corriendo en la bandeja).

### Qué hace la ventana

- Botón "Iniciar grabación de pantalla" / "Detener grabación" — reusa
  `core/recorder.py:ScreenRecorder` **tal cual** (mismo pipeline ffmpeg de
  captura de pantalla + micrófono que usa el resto de la app); no duplica esa
  lógica.
- Al detener, un campo de texto "¿Qué pasó?" para describir el problema, y un
  botón "Enviar reporte".
- Sin transcripción/resumen por IA (Groq) en este modo — solo texto libre del
  usuario, aunque el resto de la app sí lo use para actas de reunión.

### Cómo envía el reporte

Al enviar, hace directo (con `requests`, **sin** `api/client.py` — ese
cliente firma con `X-API-TOKEN` de sesión logueada, que este modo no tiene):

```
POST <server>/admin/crm_s/report_issue/submit/
Content-Type: multipart/form-data

token: <el mismo token recibido>
title: <título fijo>
description: <texto libre del usuario>
recording: <archivo .mp4>          (si se grabó algo)
```

Sin headers de auth ni cookies — el `token` es la autorización completa.
Esto **actualiza** el PQR que `start` ya creó; nunca crea uno nuevo.

Ver `ui/support_window.py` (`submit_report()` para el POST aislado de Qt,
`SupportWindow` para la ventana) y `main.py` (`parse_support_launch`,
`_run_support_mode`).

### Probar sin un link real (modo desarrollador)

Para no depender de generar un link `goujanareporte://` real (que exige un
ERP corriendo y una sesión logueada) hay un toggle oculto en el **menú de
clic derecho del ícono de la bandeja** — no está en "⚙ Configuración",
solo ahí: **"🧪 Modo soporte técnico (prueba)"** (checkbox).

- Al marcarlo, abre `SupportWindow` directamente (`test_mode=True`), sin
  pasar por `parse_support_launch()` ni por ningún link. Como en este caso
  no hay `token`/`server` reales, la propia ventana muestra dos campos de
  texto editables ("Server" y "Token de prueba") que en el modo normal
  (lanzado por el link real) **no aparecen** — ahí token/server ya vienen
  correctos en la URL y no hace falta ni tiene sentido editarlos.
- El botón "Enviar reporte" queda deshabilitado hasta que ambos campos
  tengan contenido, para que sea evidente que ese envío no llegará a ningún
  lado sin un token real emitido por `crm_s.report_issue.start`.
- Al desmarcar el checkbox ("Modo usuario"), cierra `SupportWindow` si está
  abierta — no hace falta reiniciar la app para volver a la agenda normal.

Ver `TrayApp._toggle_support_test_mode()` en `ui/tray.py` y el parámetro
`test_mode` de `SupportWindow` en `ui/support_window.py`.
