# Verificación antes de dar por terminado un cambio de UI

1. **Módulos:** `pytest tests/test_ui.py`. Carga cada módulo con Node; un error de sintaxis deja la página en blanco sin aviso.
2. **Servidor de demo:** `python scripts/demo.py --no-browser --fresh`.
3. **Recorrido en navegador** con la skill `browser-automation`, en un solo script:
   - En vivo: simular, ver entrar decisiones, abrir un detalle y cerrarlo con Esc.
   - Laboratorio: elegir un caso, aplicar un "¿Qué pasa si…?" y ver cambiar el veredicto.
   - Bandeja: rechazar con J, K y R, y deshacer.
   - Métricas: los gráficos tienen datos y sus tablas abren.
4. **Consola:** cero errores y cero peticiones fallidas.
5. **Capturas:** a 1440 y a 390 px de ancho, en modo claro y oscuro. Revisa solapamientos, textos cortados y saltos de diseño.
6. **Teclado:** se puede recorrer cada vista con Tab, y el foco siempre es visible.
7. **Movimiento reducido:** con `prefers-reduced-motion: reduce` no hay animaciones.
8. **Perfil:** con `JEV_GUARD_PROFILE=30x` los nombres cambian solos y no queda ningún nombre de empresa escrito en el front.
