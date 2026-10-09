# SafeLens Media Delivery Architecture

This note explains how media currently flows through the SafeLens system, whether everything can be served only from EC2, and which deployment pattern is best for speed and reliability.

## 1. Current Architecture

Today the system is effectively a hybrid architecture:

1. The frontend UI is deployed on AWS Amplify.
2. The Django API is deployed on EC2.
3. Incident metadata lives in PostgreSQL and is exposed by Django API endpoints such as `/api/overview/events/`.
4. Incident media can come from two places:
   - S3 URLs, when the image/video has been uploaded to S3
   - EC2 local storage, when the media is still stored on the server filesystem and exposed through `/media/...`

## 2. Current Code Paths

### API and frontend

- Frontend API base is read from:
  [frontend-dashboard/src/config.js](/home/rajanikanth/02-prodisyn-git/P004-SafeLensAI-Production/frontend-dashboard/src/config.js:1)

- Frontend media URL normalization is used by:
  [frontend-dashboard/src/components/Overview.jsx](/home/rajanikanth/02-prodisyn-git/P004-SafeLensAI-Production/frontend-dashboard/src/components/Overview.jsx:286)
  [frontend-dashboard/src/components/Analytics.jsx](/home/rajanikanth/02-prodisyn-git/P004-SafeLensAI-Production/frontend-dashboard/src/components/Analytics.jsx:252)
  [frontend-dashboard/src/components/Dashboard.jsx](/home/rajanikanth/02-prodisyn-git/P004-SafeLensAI-Production/frontend-dashboard/src/components/Dashboard.jsx:239)

### Backend media generation

- EC2 uploads files to S3 here:
  [database-api/api/utils.py](/home/rajanikanth/02-prodisyn-git/P004-SafeLensAI-Production/database-api/api/utils.py:136)

- Django converts stored media paths into browser-usable URLs here:
  [database-api/api/serializers.py](/home/rajanikanth/02-prodisyn-git/P004-SafeLensAI-Production/database-api/api/serializers.py:289)

- Django overview API assembles media URLs for the dashboard here:
  [database-api/api/views.py](/home/rajanikanth/02-prodisyn-git/P004-SafeLensAI-Production/database-api/api/views.py:92)

- Download proxy endpoint exists here:
  [database-api/api/views.py](/home/rajanikanth/02-prodisyn-git/P004-SafeLensAI-Production/database-api/api/views.py:280)

## 3. Can Everything Be Served Only From EC2?

Yes. It is possible.

That means:

1. Images and videos are stored only on EC2 disk.
2. Django or Nginx serves all media from EC2.
3. Amplify frontend requests media from EC2 URLs only.

### Advantages

- Simpler mental model
- One storage location
- Easier for quick testing

### Disadvantages

- Slower at scale because EC2 handles API plus image/video traffic
- More load on one machine
- Harder to scale when incident count grows
- Risk of disk filling up
- If EC2 goes down, API and media both go down
- Video delivery is worse than object storage/CDN delivery

## 4. Can Media Be Served Directly From S3?

Yes, and this is usually better for production.

That means:

1. EC2 handles login, business logic, database access, and JSON APIs.
2. S3 stores incident images and videos.
3. Frontend receives either:
   - full S3 URLs, or
   - S3 object keys that the frontend/backend converts into full S3 URLs

### Advantages

- Faster media delivery for large files
- Lower load on EC2
- Better durability
- Easier future CDN support through CloudFront
- Cleaner separation between API traffic and media traffic

### Disadvantages

- Slightly more configuration
- Need bucket policy, CORS, or signed URL strategy to be correct

## 5. Which Is Best?

For your project, the best production architecture is:

1. Amplify for frontend
2. EC2 for Django API
3. S3 for media

This is the best balance of speed, cost, and operational safety.

## 6. Which Is Fastest?

For media delivery, S3 is generally faster than serving images/videos through EC2, especially when:

- there are many incidents
- video files are large
- multiple users open the dashboard at the same time

For small local testing, EC2-only can feel simpler. For real deployment, hybrid is better.

## 7. Recommended Final Pattern

Use this as the target architecture:

```text
Amplify UI
   -> Django API on EC2 for JSON/auth/reviews/settings
   -> S3 for incident image/video files
```

Operationally:

- Keep API URLs in frontend env:
  - `VITE_API_BASE_URL`
- Keep S3 media settings in frontend env:
  - `VITE_AWS_STORAGE_BUCKET_NAME`
  - `VITE_AWS_S3_REGION_NAME`
- Keep backend AWS settings in EC2 env:
  - `AWS_STORAGE_BUCKET_NAME`
  - `AWS_S3_REGION_NAME`
  - `PUBLIC_BASE_URL`
  - `AMPLIFY_URL`

## 8. When To Choose EC2-Only

Choose EC2-only only if all of these are true:

- very small deployment
- low incident volume
- no large video retention requirement
- short-term internal demo

## 9. When To Choose Hybrid EC2 + S3

Choose hybrid if any of these are true:

- production usage
- many incidents per day
- users open evidence images/videos often
- long-term storage matters
- you want better performance and simpler scaling

## 10. Final Recommendation

Do not move everything to EC2 only unless you want a short-term simplification.

For your deployed AWS setup, the best and faster approach is:

- UI from Amplify
- API from EC2
- media from S3

That keeps EC2 focused on backend logic and lets S3 do what it is best at: serving files reliably and quickly.
