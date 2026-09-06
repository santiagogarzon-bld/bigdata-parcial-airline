# Inicio de proyecto

Necesito que realices una planeación de este proyecto que tiene como objetivo entender sistemas de ingestion de alta concurrencia, para analitica sin degradar la aplicacion principal que intenta emular un aeuropuerto segun define el document (ve al PDF en esta carpeta).  Analices los puntos de definicion requeridos y los dejes en un md, donde yo respondeŕe todas las preguntas. Despues de eso se hará una planeación y todo debe quedar en este repositorio. Hay un detalle importante, la cuenta a desplegar es una cuenta academy de AWS, asi que configuraciones de IAM están directamente prohibidas, Investiga este fenomeno a detalle y analiza posibles riesgos. 
Revisa los siguientes links para mas detalle de AWS Academy lab:
Vocareum AWS Academy Lab documentation (access URL/query token redacted): environment overview, management console, navigation, services, and EC2 sections.
Se cuenta solo con 45 dolares de budget (5/50 USD usados) asi que se debe tener en cuenta que se requieren bajos costos. 

Empieza la planeacion



# Respuesta a preguntas generadas por CODEX

Ya rellené algunas preguntas. Revisalas, pero quiero ser muy riguroso en la parte de preguntas funcionales, siendo lo mas cercano posible a una aerolinea. Ayudame a orientarme manteniendo rigurosdidad y tu rellenas las respuestas funcionales basado en mis respuesas.


# commit
Genial, crea un commit.


# Engine de Aerolinea 
Es hora de la planeación de desarrollo.  La idea es antes de empezar todo de manera paralela de todo al mismo tiempo, la fino es crear el motor primeramente que es el corazon de todo y antes que los demas componentes, con tests unitarios, de funcionamiento, etc. Para que sea un componente bastante confiable y que cumpla con los requerimientos funcionales. 
No vas a desarrollar tu, debes iniciar un agente al que le vas a pasar las especificaciones de lo que debe desarrollar de manera muy muy bien definida, tanto tecnica como funcionalmente que use GPT 5.6 Terra High. ADELANTE!!!

# Database hardening delegation (sanitized)

Design and harden the PostgreSQL reservation schema with Alembic as the only DDL authority. Deliver a guarded, idempotent bootstrap command, separate required catalogs from synthetic demo data, preserve booking-engine locking semantics, and prove fresh setup, repeatability, legacy upgrades, constraints, drift contract, linting and PostgreSQL concurrency tests. Do not include credentials, production URLs, AWS IAM work, or HTTP/API changes.



# Diagrama ERD base de datos OLTP
Crea el diagrama de base de datos  usando la skill  /home/nuvu-pc-n4gx/.claude/skills/drawio-skill, donde crearás el ERD (solo el .drawio) y debes dejar documentado cual es la base de datos a crear.

