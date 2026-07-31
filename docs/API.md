# API Surface (MVP)

Base: `/api`

## Projects
- POST   /projects
- GET    /projects
- GET    /projects/{project_id}
- PATCH  /projects/{project_id}
- GET    /projects/{project_id}/status

## Sources
- POST   /projects/{project_id}/sources
- GET    /projects/{project_id}/sources
- GET    /sources/{source_id}
- PATCH  /sources/{source_id}/role
- POST   /sources/{source_id}/process
- GET    /sources/{source_id}/pages/{page_number}

## Analysis
- POST   /projects/{project_id}/analyze
- GET    /projects/{project_id}/analysis
- GET    /projects/{project_id}/metrics
- GET    /projects/{project_id}/evidence-gaps

## Plans & Outline
- POST   /projects/{project_id}/plans/generate
- GET    /projects/{project_id}/plan
- PATCH  /projects/{project_id}/plan
- GET    /projects/{project_id}/outline
- PATCH  /projects/{project_id}/outline
- POST   /projects/{project_id}/outline/nodes/{node_id}/recommend
- POST   /projects/{project_id}/outline/approve  → stage PRODUCING

## Editions
- POST   /projects/{project_id}/editions
- GET    /projects/{project_id}/editions
- GET    /editions/{edition_id}
- POST   /editions/{edition_id}/produce
- POST   /editions/{edition_id}/pause
- POST   /editions/{edition_id}/resume
- GET    /editions/{edition_id}/diff/{other_edition_id}

## Sections
- GET    /editions/{edition_id}/sections
- GET    /sections/{section_id}
- PATCH  /sections/{section_id}
- GET    /sections/{section_id}/evidence
- GET    /sections/{section_id}/versions
- GET    /sections/{section_id}/reviews
- POST   /sections/{section_id}/research
- POST   /sections/{section_id}/regenerate
- POST   /sections/{section_id}/approve

## Exports
- POST   /editions/{edition_id}/exports
- GET    /editions/{edition_id}/exports
- GET    /exports/{export_id}/download

## Realtime
- WS /ws/projects/{project_id}/events  (stage, task progress, review counts)
