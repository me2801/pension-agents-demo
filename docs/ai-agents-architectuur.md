# AI-agents: architectuur en kwaliteitsprincipes

Een AI-agent is pas inzetbaar bij een pensioenuitvoerder als hij net zo is gebouwd als elk ander productiesysteem: gelaagd, getypeerd, getest en veilig. Het LLM is daarbij het kleinste onderdeel. De betrouwbaarheid wordt bepaald door de engineering eromheen.

Dit document beschrijft de cloudarchitectuur voor AI-agents en de demo-applicatie in deze repository.

## Cloudarchitectuur

De keuze van het platform hangt af van de klant.

### Enterprise: Microsoft Azure of AWS

Enterprise klanten hebben een eigen cloudomgeving. De agent wordt daarin gebouwd, zodat hij aansluit op de bestaande identity, security en beheer. De architectuur van de demo-applicatie vertaalt één-op-één naar Azure:

| Onderdeel | Demo-applicatie | Azure |
|---|---|---|
| LLM | Claude via de API | Azure OpenAI (Azure AI Foundry) |
| Agent-orkestratie | LangGraph in FastAPI | LangGraph in Azure Container Apps of Azure Functions |
| Tools van de agent | Python-functies | Azure Functions met een HTTP-trigger |
| Kennisbank (RAG) | pgvector | Azure AI Search, gevuld door data pipelines |
| State van workflows | Postgres-checkpointer | Azure Database for PostgreSQL |
| Identity | eigen JWT | Entra ID |
| Secrets | environment variables | Key Vault met managed identity |
| Tracing en evaluatie | MLflow | MLflow in Azure Machine Learning, Application Insights |
| CI/CD | GitHub Actions | GitHub Actions of Azure DevOps Pipelines |

Twee onderdelen vormen in Azure de kern van een agent:

- **Data pipelines:** een agent is zo goed als de data die hij krijgt. De kennisbank voor RAG vraagt dezelfde discipline als data engineering: betrouwbare ingest, transformatie en herhaalbare runs.
- **Azure Functions:** kleine, losse eenheden code die op een trigger draaien. Dat is precies de vorm van de tools die een agent aanroept: los te deployen, te testen en te herstellen.

### Kleinere klanten: managed services

Kleinere klanten hebben geen eigen cloudomgeving. Daar wordt gebouwd op managed services: **Supabase** voor database en authenticatie, **Render** voor backend services en **Cloudflare**. Security en database zijn de onderdelen waar zelfbouw het meeste risico oplevert, dus daar is een volwassen managed platform vaak de veiligere keuze.

## Ontwikkelproces in productie

Wijzigingen lopen via feature branches op GitHub. Elke commit wordt gereviewd en via dev en test naar prod gemerged.

## Demo-applicatie

De demo-applicatie is gevibecode: de code is geschreven door Claude en daarna geaudit op de architectuurvoorwaarden. Niet elke regel code is handmatig gereviewd. Security en database zijn in de demo bewust zelf gebouwd (JWT, bcrypt, PostgreSQL), zodat de principes zichtbaar zijn in de code. In productie ligt een platform als Supabase meer voor de hand.

### Architectuur

De applicatie bestaat uit een React-frontend, een FastAPI-backend en PostgreSQL met pgvector. Daarnaast draait MLflow voor tracing en evaluatie. De backend heeft een gelaagde architectuur met dependencies die maar één kant op lopen: transport (REST en MCP) → services → workflows en database → RAG → domain. `import-linter` dwingt dat af. Een API-route kan dus nooit rechtstreeks de database of een workflow aanroepen.

Alle agents implementeren dezelfde interface: `ChatWorkflow.stream(thread_id, message)`. De services kennen alleen die interface, waardoor workflows uitwisselbaar zijn en los te testen.

### Agents (LangChain en LangGraph)

- **Weather agent:** een agent die zelf bepaalt welke tools hij aanroept.
- **Support workflow:** een LangGraph-graph die een e-mail classificeert, parallel de deelnemer en het relevante beleid opzoekt en een concept schrijft. Een AI-reviewer controleert het concept en stuurt het hooguit twee keer terug. Daarna keurt een medewerker het goed (human-in-the-loop). Klachten worden altijd door een medewerker afgehandeld. De state staat in Postgres via de checkpointer, zodat een workflow die op goedkeuring wacht een herstart overleeft.
- **Policy assistant (RAG):** de kennis staat als Markdown-documenten in de repository. Die worden per sectie gechunkt, lokaal ge-embed met een meertalig embeddingmodel en opgeslagen in pgvector. Vragen van deelnemers verlaten daardoor de eigen infrastructuur niet. Het LLM mag alleen de opgehaalde chunks gebruiken en moet ze citeren. Levert de retrieval niets relevants op, dan wordt het LLM helemaal niet aangeroepen.

### MCP

Dezelfde services zijn ook beschikbaar via een MCP-server. AI-clients zoals Claude of een IDE gebruiken zo dezelfde workflows, met dezelfde bearer tokens en dezelfde autorisatie als de REST API.

### Codekwaliteit en complexiteitsreductie

De normen worden afgedwongen door tooling; het zijn geen afspraken op papier.

- **Kleine functies:** maximaal een cyclomatic complexity van 8, vijf argumenten en dertig statements per functie (ruff). De frontend heeft vergelijkbare limieten in eslint.
- **Lage coupling:** layer contracts in `import-linter` en interfaces (`ChatWorkflow`, `KnowledgeBase`, `ChatApi`).
- **Documentatie:** in de backend heeft elke module, class en functie een docstring (afgedwongen met de `D`-regels van ruff). De API-documentatie wordt gegenereerd uit de OpenAPI-spec.
- **Consequent gebruik van modellen:** één set Pydantic-modellen voor alle lagen. Daaruit wordt de OpenAPI-spec gegenereerd, en daaruit weer de TypeScript-types van de frontend. CI faalt zodra die uit elkaar lopen. Ook de LLM-output is getypeerd: classificatie en review leveren structured output als Pydantic-modellen.
- **Types:** mypy `--strict` in de backend en TypeScript `strict` in de frontend.

### Onderhoudbaarheid en hersteltijd

- **MLflow-tracing:** elke chat turn wordt één trace, met elke node in de graph, elke LLM- en tool-call en de opgehaalde chunks met hun scores. Bij een incident is direct zichtbaar waar het misging.
- **Request-ID's en reference-ID's:** elke request krijgt een request-ID, en errors worden gelogd met een reference-ID. De gebruiker krijgt nooit interne details te zien.
- **RAG-evaluatie:** de evaluatie meet hit rate, MRR en of off-topic vragen worden afgewezen, en logt elke run in MLflow. Zo wordt het effect van een ander model of andere chunking meetbaar en vergelijkbaar.
- **Dependency injection:** alles wordt op één plek samengesteld, in de composition root. Een fix blijft lokaal, en een andere implementatie (bijvoorbeeld een andere identity provider achter `AuthService`) raakt de rest van de code niet.

### Security by design

- Elke call naar de API en de MCP-server vereist een JWT, met validatie van signature, expiry, audience, issuer en scope.
- Autorisatie zit in de service layer. Een onbekende en een andermans conversatie geven allebei een 404, zodat er niets uitlekt.
- Secrets komen alleen uit environment variables en hebben geen defaults. Het fake LLM is alleen testcode en zit niet in de productie-image.
- Wachtwoorden worden gehasht met bcrypt. Inloggen met een onbekende gebruikersnaam duurt even lang als met een bekende, zodat niet af te tasten is welke accounts bestaan.
- LLM-output wordt gerenderd zonder raw HTML, met een strikte Content Security Policy.
- Human-in-the-loop: een medewerker keurt elk antwoord goed voordat het wordt verstuurd.
- Geen enkele container draait als root. Daarnaast secret scanning en dependency audits.

### Geautomatiseerd testen

- **Unit tests:** services, workflows met een fake LLM dat vaste antwoorden geeft (deterministisch en zonder API key), en de REST- en MCP-laag.
- **Integratietests:** tegen een echte Postgres met pgvector via Testcontainers. Ze testen onder meer dat migraties up en down werken, dat een gepauzeerde goedkeuring een herstart overleeft en dat een Nederlandse vraag het Engelse document vindt.
- **End-to-end tests:** via de API en met Playwright door de UI.
- **Coverage:** 98% voor de backend en 96% voor de frontend. CI faalt bij een coverage onder 80% en bij een score onder 0,85 op de RAG-evaluatie.

Linting, type checks en architectuurchecks draaien op drie momenten: tijdens het ontwikkelen met AI (via een hook), bij elke commit (via pre-commit) en bij elke pull request (in CI). Tests, coverage en evaluatie draaien in CI.

## Samenvatting

De agents zelf zijn klein. De kwaliteit zit in de structuur: één interface, één set modellen, afgedwongen limieten op complexiteit en coupling, en tests op elk niveau. Daardoor is de applicatie veilig genoeg voor gegevens van deelnemers, en is een bug snel te vinden en lokaal te fixen.
