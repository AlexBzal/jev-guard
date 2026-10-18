# Guion del video de demo (unos 3 minutos)

La demo usa el perfil `demo`: Nimbus, una empresa de software ficticia. Con otro perfil, los nombres cambian solos.

Cada escena indica qué se ve en pantalla y qué se dice. Los subtítulos del video grabado
resumen la narración, así que el video se entiende también sin voz.

| Tiempo | Pantalla | Narración |
|---|---|---|
| 0:00 – 0:08 | Portada: "JEV Guard" | Los agentes de IA de las empresas ya envían correos, actualizan el CRM, responden a clientes y publican contenido. Un solo error masivo cuesta caro. Esto es JEV Guard, un guardián abierto que cualquier empresa configura con su marca, su oferta y sus políticas. |
| 0:08 – 0:30 | **En vivo.** Se pulsa "Simular agentes" y se sube a 10 por segundo. | Antes de cada acción, el agente le pregunta al guardián. Aquí vemos a los agentes de Nimbus trabajando: cada tarjeta es una decisión tomada en milisegundos. |
| 0:30 – 0:45 | Indicadores de latencia y costo | El guardián resuelve solo la gran mayoría de las acciones. Cada decisión cuesta fracciones de centavo: unas 180 veces menos que usar un LLM como juez. |
| 0:45 – 1:05 | Se abre una decisión frenada | Esta acción se frenó. El guardián explica por qué en lenguaje claro, aunque JEV no escribe texto: arma las razones a partir de las preguntas que respondió. |
| 1:05 – 1:20 | **Laboratorio.** Correo correcto: "Permitida". | Veamos cómo decide. Un correo de seguimiento correcto: las reglas en código no encuentran nada y JEV responde siete preguntas tipadas en una sola llamada. |
| 1:20 – 1:40 | Se pulsa "Prometer un descuento falso": "Frenada" | Si el agente promete un descuento que la empresa no ofrece, JEV lo detecta con certeza alta y el correo se frena antes de salir. |
| 1:40 – 1:50 | Se pulsa "Inyectar una instrucción": "Frenada" | Si un correo entrante manipula al agente para filtrar la base de contactos, la señal crítica de inyección lo frena sin importar nada más. |
| 1:50 – 1:55 | Se elige "Respuesta de soporte" y se pulsa "Prometer algo fuera de política": "Frenada" | Y cada empresa puede declarar sus propias acciones sin escribir código. Esta respuesta de soporte promete un reembolso fuera de la política, y también se frena. |
| 1:55 – 2:20 | **Bandeja.** Una persona rechaza y aprueba. | Lo dudoso o de alto impacto no se decide solo: llega a esta bandeja. Una persona aprueba o rechaza, y cada decisión queda como etiqueta para calibrar los umbrales. |
| 2:20 – 2:45 | **Métricas** | Así sabemos que funciona: acciones inseguras detenidas, falsos bloqueos, precisión de la bandeja, quién decidió, latencia y costo. |
| 2:45 – 3:00 | Cierre | Reglas para lo exacto, JEV para el juicio rápido, un LLM o una persona para la duda. Un perfil YAML por empresa. Miles de decisiones al día, en milisegundos y por centavos. |

## Aclaración para el jurado

En la demo, las respuestas de JEV las produce un simulador local que imita el formato de TypeSafe. La interfaz lo indica con una franja visible. Con una clave de TypeSafe, el mismo sistema usa JEV real sin cambiar código.
