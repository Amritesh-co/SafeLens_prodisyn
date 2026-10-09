# Changelog

All notable changes to the SafeLensAI Cloud Backend API will be documented in this file.

---

## [1.1.0] - 2026-08-05

### Added

- Added support for 5 new AI use cases:
  - Sleep Detection
  - Mask Violation
  - No Goggles
  - No Gloves
  - No Boots


- Added Forgot Password functionality.
  - Password reset token generation
  - Password reset email
  - Password update API
  - Token validation

- Added Advanced Analytics APIs.
  - Pareto Analysis API
  - Safety Score by Location API
  - Incident Heatmap API
  - PPE Compliance Trend API

- Added support for dynamic dashboard summary APIs.

---

### Improved

- Improved dashboard response time.
- Improved analytics query performance.
- Improved incident aggregation logic.
- Improved serializer response consistency.
- Improved pagination performance.
- Improved notification processing.
- Improved event ingestion performance.
- Improved media retrieval performance.

---

### Changed

- Updated analytics calculations.
- Updated dashboard summary response.
- Refactored Advanced Analytics API.
- Refactored dashboard aggregation logic.
- Refactored event processing pipeline.
- Standardized API response formats.
- Optimized database queries.
- Improved JWT authentication flow.

---

### Fixed

- Fixed camera and location mapping inconsistencies.
- Fixed PPE event aggregation issues.
- Fixed incident statistics mismatch.
- Fixed analytics filtering synchronization.
- Fixed password reset token validation.
- Fixed attendance calculation edge cases.
- Fixed notification retry handling.
- Fixed serializer validation issues.
- Fixed duplicate notification generation.
- Fixed deployment configuration issues.
- Fixed production environment configuration.

---

## [1.0.0] - 2026-06-22

### Initial Release

### Added

- Django REST Framework backend.
- PostgreSQL database integration.
- JWT Authentication.
- User Management APIs.
- Role-based authorization.
- Dashboard APIs.
- Incident Management APIs.
- Event Management APIs.
- Camera Management APIs.
- Settings Management APIs.
- Notification Management APIs.
- Email notification support.
- SMS notification support.
- WhatsApp notification support.
- Media upload and retrieval APIs.
- Image and video serving.
- Incident review workflow.
- Event polling service.
- AWS deployment configuration.
- Environment variable configuration.
- Logging configuration.
- Production-ready API structure.
- API documentation.
- Deployment scripts.
- Initial database migrations.