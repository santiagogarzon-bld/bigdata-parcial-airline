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


# Procesos paralelos para desarrollo

Usando agentes paralelos, y ya teniendo el motor de funcionamiento de la aerolinea que es el corazon del mvp, implementa los gaps faltantes para llegar a la aplicacion MVP. El objetivo es un MVP operacional basado en PostgreSQL OLTP. No debes implementar todavía la parte analitica. Buscamos es tener una aplicaicon de aerolinea funcional, para despues sobre eso aplicar la analitica, igual a como se haría en una empresa real. Primero aplicacion funcional despues analitica, pero para el scope de esta sesión solo aplicacion. Los agentes deben ser GPT5.6 Luna con effort medium donde les pases de manera muy detallada, factual y concreta de lo que se debe realizar.

(Aqui se creo un plan y se valido antes de empezar el desarrollo del código)


# MVP analitica
Actúa como Arquitecto de Datos y Especialista en Cloud/AWS. Actualmente tenemos una aplicación transaccional desplegada en AWS y funcional. El siguiente paso es implementar la capa de analítica de datos. Con los requerimientos ya definidos usando modelos paralelos de gpt 5.6 luna con effort medium  implementa los gaps faltantes para llegar a la versión con analitica  con ETL's. Donde debe haber en la RDS un schema para analitica (revisa este eschema). Debes actuar como supervisor de los modelos, los commits se hacen al final cuando ya hayas validado que todo esté correcto. Ten en cuenta que por ahora solo vamos a hacer la capa de analitica de datos, es decir el data engineering, no la parte de Analisis en si mismo. El objetivo es preparar una arquitectura para que podamos hacer analitica mas adelante.


# Scheduler ETL
Haz que se ejecute cada hora con un scheduler.


# Diagramas y documentación analítica

Usando la skill `/home/nuvu-pc-n4gx/.claude/skills/drawio-skill`, crea un
diagrama simple y minimalista del flujo ETL, otro del flujo de datos y una
arquitectura AWS integral de la aplicación y la capa analítica. Los diagramas
deben usar iconos y leyendas breves sin omitir detalles importantes. Centraliza
todos los archivos Draw.io en `diagramas/` y agrega documentación detallada de
la capa analítica.
