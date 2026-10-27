# Diagrams (HLD + LLD)

Mermaid diagrams; GitHub renders them inline. Text source of truth stays in `docs/ARCHITECTURE.md`
and `docs/API_CONTRACTS.md` — if a diagram disagrees with those, the docs win.

Contents
1. HLD — system context
2. HLD — pipeline and gating
3. HLD — deployment
4. LLD — scan sequence (end to end)
5. LLD — backend modules
6. LLD — reachability algorithm
7. LLD — fix engine state machine
8. LLD — data model (ER)
9. LLD — status enums
10. LLD — frontend routes and data flow
11. Delivery — task dependency graph

---

## 1. HLD — system context
```mermaid
flowchart LR
    subgraph Triggers
        B1[Boomi B1<br/>daily schedule]
        UI[Dashboard<br/>Run scan]
    end

    subgraph PatchPilot["PatchPilot (FastAPI engine)"]
        API[REST API + SSE]
        PIPE[Pipeline<br/>clone → scan → symbols → reachability → risk → fix → pr → notify]
        DB[(SQLite)]
    end

    subgraph External
        GH[(GitHub<br/>client repos)]
        OSV[OSV-Scanner / OSV.dev]
        TI[CISA KEV feed<br/>FIRST EPSS API]
        LLM[LLM provider<br/>keys at kickoff]
    end

    subgraph Boomi["Boomi (built with Boomi Companion)"]
        B2[B2 Finding notification]
        B3[B3 Scan summary]
        B4[B4 Compliance report]
        JIRA[Jira]
        SLACK[Slack]
        LOG[(Compliance log)]
    end

    B1 -- "POST /api/scans<br/>X-API-Key" --> API
    UI -- "POST /api/scans" --> API
    API --> PIPE
    PIPE <--> DB
    PIPE -- clone / push branch / open PR --> GH
    PIPE -- vulnerable deps --> OSV
    PIPE -- exploit data --> TI
    PIPE -- JSON prompts --> LLM
    API -- "SSE progress" --> UI
    PIPE -- "POST /patchpilot/findings" --> B2
    PIPE -- "POST /patchpilot/scan-summary" --> B3
    API -- "GET /patchpilot/compliance" --> B4
    B2 --> JIRA
    B2 --> SLACK
    B2 --> LOG
    B3 --> SLACK
    B4 --> LOG
```

## 2. HLD — pipeline and gating
Only `reachable` findings, and `unsure` with confidence ≥ 0.5, go on to fix / PR / notify automatically.
```mermaid
flowchart TD
    A[clone<br/>cloner.py] --> B[detect languages + scan + threat intel<br/>ecosystems.py · scanner.py · OSV<br/>threat_intel.py · KEV, EPSS]
    B --> C[symbols<br/>symbols.py · LLM]
    C --> D[reachability<br/>reachability.py · AST + LLM]
    D --> E[risk<br/>risk.py]
    E --> G{reachable?<br/>or unsure ≥ 0.5}
    G -- no --> K[record finding<br/>status open, no action]
    G -- yes, auto_fix=false --> O[notify only<br/>event finding.open]
    O --> S
    G -- yes, auto_fix --> F[fix per package<br/>fixer.py · upgrade, pytest, AI patch]
    F --> H{tests pass?}
    H -- yes --> P[pr<br/>github_pr.py]
    H -- no after 2 retries --> N[needs_human]
    P --> Q[notify<br/>boomi_client.py → B2]
    N --> Q
    K --> S
    Q --> S[scan done<br/>→ B3 summary]
```

## 3. HLD — deployment
```mermaid
flowchart LR
    Judge[Judges / team browser] -->|HTTPS| FE[Vercel<br/>React build<br/>VITE_API_BASE_URL]
    FE -->|HTTPS REST + SSE| BE
    subgraph Host["Render or Railway (Docker)"]
        BE[FastAPI container<br/>python:3.11-slim + git + osv-scanner<br/>non-root, healthcheck]
        SQL[(SQLite file)]
        TMP["/tmp/patchpilot/scan_id<br/>temp venvs"]
        BE --- SQL
        BE --- TMP
    end
    BoomiCloud[Boomi Atom / Cloud] -->|B1 POST /api/scans| BE
    BE -->|B2 / B3 / B4| BoomiCloud
    BE --> GitHub[(GitHub)]
    BE --> LLMAPI[LLM API]

    subgraph Fallback["Fallback if host fails"]
        Laptop[Laptop: uvicorn :8000] --> CF[cloudflared tunnel<br/>public URL]
    end
```

## 4. LLD — scan sequence (end to end)
```mermaid
sequenceDiagram
    autonumber
    actor User as Dashboard / Boomi B1
    participant API as FastAPI /api
    participant Bus as Event bus (SSE)
    participant Pipe as pipeline.py
    participant Svc as services/*
    participant LLM as llm.py
    participant GH as GitHub
    participant Boomi as Boomi B2/B3
    participant DB as SQLite

    User->>API: POST /api/scans {client_name, repo_url, branch, auto_fix}
    API->>DB: insert scan (queued)
    API-->>User: 202 {scan_id, status: queued}
    API->>Pipe: background task run(scan_id)
    User->>API: GET /api/scans/{id}/events
    API->>Bus: subscribe(scan_id)

    Pipe->>Svc: cloner.clone(repo_url, branch)
    Svc->>GH: git clone to /tmp/patchpilot/{scan_id}/repo
    Pipe->>Bus: {stage: clone, status: done}
    Pipe->>Svc: scanner.scan(path)
    Svc-->>Pipe: list[RawVuln]
    Pipe->>Svc: threat_intel.enrich(vulns) · CISA KEV + EPSS
    Pipe->>Bus: {stage: scan, progress}

    loop each RawVuln
        Pipe->>LLM: extract_symbols
        LLM-->>Pipe: symbols[]
        Pipe->>Svc: reachability.analyze(path, symbols)
        alt AST matches found
            Svc->>LLM: reachability_verdict(evidence)
            LLM-->>Svc: {reachability, confidence, explanation}
        else no matches
            Svc-->>Pipe: not_reachable (no LLM call)
        end
        Pipe->>Svc: risk.score(cvss, verdict, in_route)
        Pipe->>DB: upsert finding
        Pipe->>Bus: {stage: reachability / risk}
    end

    loop each package with reachable findings (auto_fix)
        Pipe->>Svc: fixer.fix(package, findings)
        Svc-->>Pipe: FixResult {new_version, patch_diff, tests_passed, attempts}
        opt tests_passed
            Pipe->>GH: github_pr.open(branch patchpilot/package-version)
            GH-->>Pipe: pr_url
        end
    end
    loop each routed finding
        Pipe->>Boomi: POST /patchpilot/findings (B2)
        Boomi-->>Pipe: {jira_key, jira_url, slack_sent, compliance_log_id}
        Pipe->>DB: insert integration_event, update finding
    end

    Pipe->>Boomi: POST /patchpilot/scan-summary (B3)
    Pipe->>DB: scan completed + stats
    Pipe->>Bus: {stage: done}
    Bus-->>User: SSE stream closes
```

## 5. LLD — backend modules
```mermaid
flowchart TB
    main[app/main.py<br/>FastAPI app, CORS, routers]
    subgraph api[app/api]
        scans[scans.py]
        findings[findings.py]
        integrations[integrations.py]
        demo[demo.py]
    end
    subgraph core[app/core]
        config[config.py<br/>pydantic-settings]
        db[db.py<br/>SQLite engine]
        events[events.py<br/>pub/sub per scan_id]
        logging[logging.py]
    end
    subgraph models[app/models]
        tables[SQLModel tables]
        schemas[Pydantic schemas = contracts]
    end
    pipeline[app/pipeline.py<br/>orchestrator]
    subgraph services[app/services]
        cloner
        ecosystems
        scanner
        threat_intel
        symbols
        reachability
        risk
        fixer
        github_pr
        boomi_client
        llm[llm.py<br/>only LLM entry point]
    end
    prompts[(app/prompts/*.md)]

    main --> api
    api --> models
    api --> pipeline
    api --> events
    pipeline --> services
    pipeline --> events
    pipeline --> db
    symbols --> llm
    reachability --> llm
    fixer --> llm
    llm --> prompts
    services --> config
    boomi_client --> db
```

## 6. LLD — reachability algorithm
```mermaid
flowchart TD
    S[Start: repo path + VulnSymbols]
    W[Walk *.py<br/>skip venv, tests, migrations]
    S --> LANG{Python?}
    LANG -- no --> GEN[Generic: import regex + symbol text search<br/>→ LLM verdict, confidence ≤ 0.8]
    GEN --> O
    LANG -- yes --> W
    W --> P[ast.parse each file]
    P --> M[Build import alias map<br/>import yaml as y → y = yaml<br/>from yaml import load → load = yaml.load]
    M --> C[Collect every ast.Call<br/>resolve dotted name via alias map]
    C --> X{matches a<br/>vulnerable symbol?}
    X -- none in repo --> NR[not_reachable<br/>no LLM call]
    X -- yes --> E[Evidence per match<br/>file, line, ±15 lines snippet]
    E --> R{enclosing function has<br/>@app.route / @app.get / @router.post …?}
    R -- yes --> IR[in_route = true]
    R -- no --> NIR[in_route = false]
    IR --> V[LLM reachability_verdict<br/>e.g. Loader=SafeLoader → safe]
    NIR --> V
    V --> O[Verdict: reachable / unsure / not_reachable<br/>+ confidence + explanation]
```

Risk: `score = min(10, cvss × reach_w × exposure_w × threat_w)`; reach_w 1.0 / 0.6 / 0.3; exposure_w 1.5 if any `in_route`;
threat_w 1.3 if in CISA KEV, 1.1 if EPSS percentile ≥ 0.9.
Priority ≥9 P1, ≥7 P2, ≥4 P3, else P4.

## 7. LLD — fix engine state machine
```mermaid
stateDiagram-v2
    [*] --> Prepare: copy repo, branch patchpilot/package-version
    Prepare --> Bump: requirements.txt → smallest fixed version
    Bump --> Install: venv + pip install (180 s)
    Install --> Bump: install fails, try next release (max 3)
    Install --> Test: pytest -q (120 s)
    Test --> Fixed: pass
    Test --> AIPatch: fail and attempts < 2
    AIPatch --> Test: apply unified diff (git apply --3way)
    Test --> NeedsHuman: fail and attempts = 2
    Fixed --> [*]: FixResult tests_passed=true → PR
    NeedsHuman --> [*]: status needs_human → still notify Boomi
```

## 8. LLD — data model (ER)
```mermaid
erDiagram
    SCANS ||--o{ FINDINGS : has
    SCANS ||--o{ FIXES : has
    FIXES ||--o{ FINDINGS : "fixes (one per package)"
    FINDINGS ||--o{ INTEGRATION_EVENTS : logs

    SCANS {
        string id PK
        string client_name
        string repo_url
        string branch
        bool auto_fix
        string owner_email
        string status
        string current_stage
        datetime started_at
        datetime finished_at
        int total_alerts
        int reachable_count
        int p1_count
    }
    FINDINGS {
        string id PK
        string scan_id FK
        string fix_id FK
        string cve_id
        json aliases_json
        string package
        string installed_version
        string fixed_version
        string summary
        float cvss
        bool kev
        date kev_date_added
        float epss
        float epss_percentile
        json vulnerable_symbols_json
        string reachability
        float confidence
        json evidence_json
        text ai_explanation
        float score
        string priority
        string status
        string jira_key
        string jira_url
        bool slack_sent
        string compliance_log_id
        json timeline_json
    }
    FIXES {
        string id PK
        string scan_id FK
        string package
        string new_version
        text patch_diff
        bool tests_passed
        int attempts
        string pr_url
        string status
    }
    INTEGRATION_EVENTS {
        int id PK
        string finding_id FK "nullable for B3/B4"
        string process "B1-B4"
        string direction
        string endpoint
        json request_json
        json response_json
        int status_code
        bool ok
        string summary
        datetime created_at
    }
```

## 9. LLD — status enums
```mermaid
stateDiagram-v2
    state "scan.status" as scan {
        [*] --> queued
        queued --> running
        running --> completed
        running --> failed
    }
    state "finding.status" as finding {
        [*] --> open
        open --> fixing: auto_fix or POST /fix
        fixing --> fixed
        fixing --> needs_human
        open --> ignored
    }
```

## 10. LLD — frontend routes and data flow
```mermaid
flowchart LR
    subgraph Shell["App shell (T11): sidebar, top bar, mode badges"]
        O["/ Overview (T12)<br/>hero stats · noise funnel · recent scans · Run scan modal"]
        L["/scans/:id Live scan (T12)<br/>pipeline stepper · log stream · findings table"]
        F["/findings/:id Finding (T13)<br/>score ring · evidence viewer · fix card · integration card · timeline"]
        I["/integrations (T14)<br/>B1–B4 cards · activity feed"]
        C["/compliance (T14)<br/>per-client table · CSV export"]
    end
    O -- Run scan --> L
    L -- row click --> F
    api[src/lib/api.ts] --> O & L & F & I & C
    mock[src/lib/mock/*<br/>VITE_USE_MOCK=true] -.-> api
    api -->|REST + EventSource| BE[(Backend /api)]
```

## 11. Delivery — task dependency graph
Model / effort per task is in brackets. Queue after each task: `tasks/BOARD.md` → "Task queue".
```mermaid
flowchart LR
    T00["T00 scaffold<br/>Sonnet · high"]
    T01["T01 data<br/>Sonnet · med"]
    T02["T02 scanner<br/>Sonnet · med"]
    T03["T03 pipeline<br/>Opus · high"]
    T04["T04 LLM client<br/>Sonnet · med"]
    T05["T05 symbols<br/>Sonnet · med"]
    T06["T06 reachability<br/>Opus · high"]
    T07["T07 risk<br/>Haiku · low"]
    T08["T08 fixer<br/>Opus · high"]
    T09["T09 GitHub PR<br/>Sonnet · med"]
    T10["T10 Boomi client<br/>Sonnet · med"]
    T11["T11 UI shell<br/>Sonnet · med"]
    T12["T12 overview + scan<br/>Sonnet · med"]
    T13["T13 finding page<br/>Sonnet · med"]
    T14["T14 integrations<br/>Haiku · low"]
    T15["T15 demo target<br/>Haiku · low"]
    T16["T16 deploy<br/>Sonnet · med"]
    T17["T17 end-to-end<br/>Opus · high"]
    T18["T18 polish<br/>Sonnet · med"]

    T00 --> T01 & T02 & T04 & T07 & T10 & T11
    T01 & T02 --> T03
    T04 --> T05 --> T06
    T04 --> T08 --> T09
    T03 & T11 --> T16
    T11 --> T12 & T13 & T14
    T03 & T06 & T08 & T09 & T10 & T12 & T13 --> T17
    T15 -.-> T17
    T16 --> T17
    T07 --> T03
    T17 --> T18
```
