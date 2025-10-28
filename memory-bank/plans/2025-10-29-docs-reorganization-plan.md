# Documentation Reorganization Plan

**Date**: 2025-10-29
**Status**: Approved
**Approach**: Option 1 - Hierarchical Documentation Structure

## Problem Statement

Project documentation has grown organically, resulting in:
- Content overlap across 9 root-level markdown files
- Inconsistent organization (some docs in root, others in `docs/`)
- Duplicate dependency information (requirements.txt + requirements-docker.txt)
- Hard to navigate and find information
- Mixed languages (English/Russian)

## Goals

1. Clear hierarchical documentation structure organized by audience
2. Eliminate content overlaps and redundancies
3. Simplify configuration files (single requirements.txt)
4. Easy navigation with clear entry points
5. Scalable structure for future growth

## Selected Approach

**Option 1: Hierarchical Documentation Structure**
- Organize by audience: getting-started, development, deployment, research
- Consolidate overlapping content
- Create navigation index
- Standard industry structure

**Additional: Requirements File Simplification (Variant A)**
- Rename `requirements-docker.txt` → `requirements.txt`
- Delete unused `requirements.txt`
- Update scripts and Dockerfile
- Single source of truth for Docker dependencies

## Implementation Steps

### Phase 1: Requirements Files Simplification

**1.1 Backup current state**
```bash
git checkout -b docs/reorganize-documentation
```

**1.2 Update update-requirements.sh script**
- Remove generation of base requirements.txt
- Generate only requirements.txt with faster-whisper extras
- Remove requirements-full.txt generation (not used)

**1.3 Update Dockerfile**
- Change: `COPY requirements-docker.txt requirements.txt`
- To: `COPY requirements.txt requirements.txt`

**1.4 Regenerate and cleanup**
```bash
./scripts/update-requirements.sh
rm requirements-docker.txt  # Will be replaced by requirements.txt
```

**1.5 Update documentation references**
- docs/DEPENDENCIES.md: Update file references
- README.md: Update Docker section

### Phase 2: Create New Documentation Structure

**2.1 Create directory structure**
```
docs/
├── README.md                    # Navigation index
├── getting-started/
│   ├── installation.md
│   ├── configuration.md
│   └── quick-start.md
├── development/
│   ├── dependencies.md
│   ├── testing.md
│   ├── architecture.md
│   └── git-workflow.md
├── deployment/
│   ├── docker.md
│   ├── vps-setup.md
│   ├── cicd.md
│   └── troubleshooting.md
└── research/
    └── benchmarks/
```

**2.2 Files to keep in root**
- README.md (trimmed to ~100 lines)
- CLAUDE.md (Claude Code entry point)
- AGENTS.md (AI agent guidance)
- LICENSE
- .gitignore, .dockerignore, etc.

**2.3 Files to move/consolidate**
- TESTING.md → docs/development/testing.md
- VPS_SETUP.md → docs/deployment/vps-setup.md
- DEPLOYMENT.md → docs/deployment/cicd.md
- docs/DEPENDENCIES.md → docs/development/dependencies.md
- .github/WORKFLOW.md → docs/development/git-workflow.md
- docs/quality_compare/* → docs/research/benchmarks/

**2.4 Files to remove**
- run.sh (replace with documentation)

**2.5 Files to keep as-is**
- Makefile (document better in docs/development/)
- pyproject.toml, poetry.lock
- docker-compose*.yml
- .github/workflows/*
- memory-bank/* (Claude context system)

### Phase 3: Content Consolidation

**3.1 docs/getting-started/installation.md**
Source content from:
- README.md "Быстрый старт" section
- README.md "Установка зависимостей" section

Structure:
- Prerequisites
- Local development setup
- Docker setup
- Verification steps

**3.2 docs/getting-started/configuration.md**
Source content from:
- README.md "Конфигурация" section
- README.md table of settings
- .env.example explanation

Structure:
- Configuration overview
- Required settings
- Optional settings
- Environment-specific configs

**3.3 docs/getting-started/quick-start.md**
Source content from:
- README.md "Быстрый старт" section
- README.md "Тестирование" section

Structure:
- 5-minute quick start
- First bot interaction
- Common commands
- Next steps

**3.4 docs/deployment/docker.md**
Source content from:
- README.md "Docker" section
- DEPLOYMENT.md Docker-related content

Structure:
- Docker quick start
- Building images
- Running containers
- Resource limits
- Troubleshooting

**3.5 docs/deployment/vps-setup.md**
Source: VPS_SETUP.md (move as-is, minor formatting)

**3.6 docs/deployment/cicd.md**
Source: DEPLOYMENT.md (focus on CI/CD pipeline)

Structure:
- CI/CD overview
- GitHub Actions setup
- Secrets configuration
- Deployment workflow
- Monitoring deployments

**3.7 docs/deployment/troubleshooting.md**
Source content from:
- DEPLOYMENT.md troubleshooting sections
- VPS_SETUP.md troubleshooting sections
- Common issues from all docs

Structure:
- Common issues
- Build failures
- Deployment failures
- Runtime issues
- Performance issues

**3.8 docs/development/testing.md**
Source: TESTING.md (move with minor updates)

**3.9 docs/development/dependencies.md**
Source: docs/DEPENDENCIES.md (move as-is)
Update: requirements.txt references (remove -docker suffix)

**3.10 docs/development/git-workflow.md**
Source: .github/WORKFLOW.md (move as-is)

**3.11 docs/development/architecture.md**
Source content from:
- README.md "Структура проекта" section
- README.md "Технологии" section

Structure:
- System architecture
- Project structure
- Key components
- Data flow
- Design patterns

**3.12 Root README.md (trimmed)**
Keep only:
- Project title and description
- Features (brief list)
- Quick links to documentation
- Installation (link to docs)
- Quick start (5 lines)
- Links to deployment docs
- Contributing
- License

Target: ~100-150 lines max

### Phase 4: Create Navigation

**4.1 docs/README.md**
Create comprehensive index:
- Welcome section
- Documentation structure
- Quick links by role (user, developer, operator)
- How to contribute to docs

**4.2 Add navigation breadcrumbs**
Each doc file should have:
- Back to documentation index link
- Related docs links

### Phase 5: Update References

**5.1 Internal links**
Update all markdown links to new locations:
- README.md → docs/* links
- CLAUDE.md → docs/* links
- Cross-references between docs

**5.2 GitHub references**
- .github/workflows/*.yml comments
- PR templates (if any)

**5.3 Memory Bank references**
- Update techContext.md if needed
- Update activeContext.md with new structure
- Note changes in progress.md

### Phase 6: Validation

**6.1 Link validation**
- Check all internal markdown links work
- Verify relative paths correct
- Test GitHub rendering

**6.2 CI/CD validation**
- Ensure workflows still reference correct files
- Test Docker build works with new requirements.txt
- Verify deployment scripts work

**6.3 Documentation review**
- Read through each doc for flow
- Check no broken cross-references
- Verify navigation makes sense

## Success Criteria

- [ ] Single requirements.txt file (no -docker suffix)
- [ ] All documentation in docs/* (except CLAUDE.md, AGENTS.md)
- [ ] Root README.md < 150 lines
- [ ] docs/README.md navigation index exists
- [ ] All internal links work
- [ ] No content duplication
- [ ] Docker build succeeds
- [ ] CI/CD pipeline works
- [ ] Memory Bank updated

## Risks & Mitigation

**Risk**: Breaking CI/CD pipelines
**Mitigation**:
- Test locally first
- Review workflow files before committing
- Can revert quickly (single branch)

**Risk**: Broken links after reorganization
**Mitigation**:
- Systematic link updates
- Use find/grep to locate all references
- Test GitHub rendering

**Risk**: Lost content during consolidation
**Mitigation**:
- Work in feature branch
- Review diffs carefully
- Keep backups of original files

## Timeline

**Total estimated time**: 3-4 hours

- Phase 1 (Requirements): 30 min
- Phase 2 (Structure): 30 min
- Phase 3 (Consolidation): 90 min
- Phase 4 (Navigation): 20 min
- Phase 5 (References): 30 min
- Phase 6 (Validation): 30 min

## Rollback Plan

If issues arise:
```bash
git checkout main
git branch -D docs/reorganize-documentation
```

All changes are in a single feature branch, easy to discard.

## Follow-up Tasks

After successful reorganization:
1. Monitor for issues in next 2-3 days
2. Update Memory Bank with learnings
3. Consider language consistency (English vs Russian)
4. Evaluate MkDocs/Docusaurus for future (optional)

## Notes

- Preserve Russian language in user-facing content where appropriate
- Keep technical docs in English for broader audience
- Memory Bank stays as-is (Claude Code system)
- Can iterate and improve after initial reorganization
