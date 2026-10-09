# SafeLensAI Documentation Index

This is the best entry point for the SafeLensAI documentation set.

The files are numbered so a new developer, operator, or handover recipient can
read them in a sensible order instead of guessing which guide matters first.

## Recommended Reading Order

0. `00_PRODUCT_SPECIFICATION.docx`
   Original product and business requirements.
1. `01_START_HERE.md`
   This index and reading plan.
2. `02_LEARNING_ROADMAP.md`
   Optional background reading for Django and DRF beginners.
3. `03_DEVELOPER_HANDBOOK.md`
   High-level project overview, stack, and basic run instructions.
4. `04_COMPREHENSIVE_SYSTEM_ARCHITECTURE.md`
   Big-picture architecture across frontend, backend, AI engine, and database.
5. `05_PROJECT_ARCHITECTURE_AND_CODE_WALKTHROUGH.md`
   Backend structure and request-flow walkthrough.
6. `06_DEVELOPMENT_GUIDE.md`
   Implementation history and reasoning behind complex backend behavior.
7. `07_RUN_AND_VERIFY.md`
   Practical local run steps and quick verification flow.
8. `08_API_DOCUMENTATION.md`
   Endpoint reference and API usage notes.
9. `09_UI_DOCUMENTATION.md`
   Frontend behavior and API interaction mapping.
10. `10_NOTIFICATION_ARCHITECTURE.md`
    Email, SMS, and WhatsApp notification flow.
11. `11_USER_MANAGEMENT_GUIDE.md`
    Admin panel and user/profile management.
12. `12_TESTING_GUIDE.md`
    Test and validation scenarios.
13. `13_DEPLOYMENT_GUIDE.md`
    Deployment constraints and hosting considerations.
14. `14_PRODUCTION_HANDOVER_MANUAL.md`
    EC2-side setup and operational handover summary.
15. `15_WHATSAPP_RETRY_OPERATIONS.md`
    WhatsApp retry operations and safety checks.
16. `database/16_RDS_PROVISIONING_GUIDE.md`
    First-time AWS RDS bootstrap from EC2.
17. `database/17_LOCAL_DB_CREATE_SCHEMA.sql`
    Local PostgreSQL schema bootstrap script.
18. `database/18_PRODUCTION_SCHEMA.sql`
    Production schema bootstrap script.
19. `database/19_PRODUCTION_SCHEMA_FIX.sql`
    Production schema fix/update script.

## Which Document To Use

Use this path if you want to run the API locally with a local PostgreSQL database:

- Read `07_RUN_AND_VERIFY.md`
- Bootstrap schema with `database/17_LOCAL_DB_CREATE_SCHEMA.sql`
- Use `08_API_DOCUMENTATION.md` for endpoints

Use this path if you want to run the API locally but connect to an existing remote database:

- Read `07_RUN_AND_VERIFY.md`
- Override `DB_HOST`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`
- Use `08_API_DOCUMENTATION.md` for endpoint testing

Use this path if you want to understand or maintain the EC2 production server:

- Read `14_PRODUCTION_HANDOVER_MANUAL.md`
- Read `13_DEPLOYMENT_GUIDE.md`
- Read `database/16_RDS_PROVISIONING_GUIDE.md`
- Use `database/18_PRODUCTION_SCHEMA.sql` and `database/19_PRODUCTION_SCHEMA_FIX.sql` as needed

Use this path if you need to understand business flow before touching code:

- Read `00_PRODUCT_SPECIFICATION.docx`
- Read `04_COMPREHENSIVE_SYSTEM_ARCHITECTURE.md`
- Read `05_PROJECT_ARCHITECTURE_AND_CODE_WALKTHROUGH.md`

## Notes

- `08_API_DOCUMENTATION.md` is the API reference, not the full deployment guide.
- `14_PRODUCTION_HANDOVER_MANUAL.md` is the main EC2 and production operations handover.
- `07_RUN_AND_VERIFY.md` is the main document for local startup and verification.
