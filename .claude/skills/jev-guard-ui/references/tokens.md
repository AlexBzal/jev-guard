# Tokens del sistema

Viven en `:root` de `ui/css/app.css`. El modo oscuro es una selección propia de valores, no una inversión.

## Color

| Rol | Claro | Oscuro | Uso |
|---|---|---|---|
| `--page` | `#f6f6f3` | `#0d0d0d` | Fondo de la aplicación |
| `--surface` | `#ffffff` | `#1a1a19` | Tarjetas, paneles, gráficos |
| `--surface-2` | `#f0efeb` | `#232321` | Controles en reposo, filas alternas |
| `--surface-3` | `#e8e7e2` | `#2c2c2a` | Hover de controles |
| `--ink` | `#0b0b0b` | `#f0efec` | Texto principal |
| `--ink-2` | `#52514e` | `#c3c2b7` | Texto secundario |
| `--muted` | `#898781` | `#8f8d86` | Etiquetas, ejes, metadatos |
| `--grid` | `#e6e5df` | `#2c2c2a` | Líneas de guía, separadores |
| `--axis` | `#c3c2b7` | `#3d3d3a` | Líneas base |
| `--border` | `rgba(11,11,11,.09)` | `rgba(255,255,255,.09)` | Anillo de 1 px |
| `--accent` | `#2a78d6` | `#3987e5` | Acción primaria, foco, serie única |
| `--accent-wash` | accent al 10 % | accent al 16 % | Selección, fondos suaves |

Estados, fijos en ambos modos y siempre con ícono y texto:

| Rol | Hex | Significado |
|---|---|---|
| `--good` | `#0ca30c` | Permitida |
| `--warning` | `#fab219` | Retenida, espera a una persona |
| `--critical` | `#d03b3b` | Frenada |

## Tipografía

Una sola familia: `system-ui, -apple-system, "Segoe UI", sans-serif`. Cifras tabulares solo en columnas y ejes.

| Token | Tamaño / interlineado | Uso |
|---|---|---|
| `--t-hero` | 44 / 1.05, 650 | Una cifra principal por vista |
| `--t-h1` | 22 / 1.25, 650 | Título de la vista |
| `--t-h2` | 15 / 1.35, 600 | Título de tarjeta |
| `--t-body` | 14 / 1.5 | Texto general |
| `--t-small` | 13 / 1.45 | Texto secundario |
| `--t-micro` | 12 / 1.4 | Metadatos, ejes, etiquetas |

## Espacio, forma y profundidad

- Escala de 4 px: `--s1` 4, `--s2` 8, `--s3` 12, `--s4` 16, `--s5` 24, `--s6` 32, `--s7` 48.
- Radios: `--r-sm` 6 (chips), `--r-md` 10 (controles), `--r-lg` 14 (tarjetas), `--r-pill` 999.
- Sombras: `--e1` para tarjetas en reposo, `--e2` para paneles flotantes y el panel lateral.
- Capas: barra lateral 20, encabezado fijo 25, panel lateral 40, diálogos 50, tooltip 60, avisos 70.

## Movimiento

| Token | Duración | Uso |
|---|---|---|
| `--m-fast` | 120 ms | Hover, pulsación |
| `--m-base` | 200 ms | Aparición de filas, cambios de estado |
| `--m-slow` | 320 ms | Panel lateral, transición entre vistas |

Curva por defecto: `cubic-bezier(.2,.8,.2,1)`. Con `prefers-reduced-motion: reduce`, todas las duraciones pasan a 0.

## Diseño de la aplicación

- Barra lateral de 232 px con navegación, empresa activa y estado del motor. Bajo 900 px se convierte en barra inferior con íconos.
- Contenido con ancho máximo de 1240 px y márgenes de 32 px, o de 16 px en móvil.
- Rejilla de 12 columnas con separación de 16 px.
