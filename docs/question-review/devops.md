# DevOps questions — team review

For each question: check the marked answer and the explanation. If it is right, write your name after **Approved by**. If something is wrong, write the fix after **Correction** instead (the question is retired and replaced). Then run `make question-approve FILE=docs/question-review/devops.md`.

## devops-legacy-01

Containers (Docker) · difficulty 1 · independent solve passed

What is the role of a Dockerfile?

- A. Monitoring
- B. Describing step by step how to build an image ✔
- C. Running containers
- D. Storing logs

Explanation: A Dockerfile is the recipe of instructions Docker follows to build an image: base image, files, dependencies and the start command.

Approved by: ______

Correction: ______

## devops-legacy-02

Deployment and configuration · difficulty 1 · independent solve passed

What is the purpose of a staging environment?

- A. Production traffic
- B. Storing backups
- C. Local development only
- D. Testing a release in a production-like setting before it goes live ✔

Explanation: Staging mirrors production closely so a release can be tested, including configuration and migrations, before real users see it.

Approved by: ______

Correction: ______

## devops-legacy-03

Deployment and configuration · difficulty 1 · independent solve passed

Where should secrets such as database passwords live?

- A. In environment variables or a secrets manager, never in code ✔
- B. In a public bucket
- C. In the Docker image
- D. In the Git repository

Explanation: Secrets belong in environment variables injected at runtime or in a secrets manager. In code, images or repositories they leak to anyone with access and live on in history.

Approved by: ______

Correction: ______

## devops-legacy-04

CI/CD · difficulty 1 · independent solve passed

What does a lock file (e.g. requirements.lock) help with?

- A. Security only
- B. Reproducible builds with exact dependency versions ✔
- C. Encryption
- D. Faster networking

Explanation: A lock file pins the exact version of every dependency, so CI and production install the same packages and builds are reproducible.

Approved by: ______

Correction: ______

## devops-legacy-05

Containers (Docker) · difficulty 1 · independent solve passed

What is the main benefit of containerising an application with Docker?

- A. It packages the app with its dependencies so it runs the same everywhere ✔
- B. It makes code faster
- C. It removes the need for tests
- D. It replaces version control

Explanation: A container image bundles the application with its runtime and libraries, so it behaves the same on a laptop, in CI and in production.

Approved by: ______

Correction: ______

## devops-legacy-06

CI/CD · difficulty 1 · independent solve passed

What is continuous integration (CI)?

- A. Deploying once a year
- B. Manual testing
- C. Automatically building and testing every change merged into the shared branch ✔
- D. Writing documentation

Explanation: CI automatically builds and tests each change merged into the shared branch (and usually each pull request), catching integration problems early.

Approved by: ______

Correction: ______

## devops-legacy-07

Monitoring and logs · difficulty 1 · independent solve passed

What does a health check in a container orchestrator do?

- A. Reports whether the service is working so it can be restarted or taken out of rotation ✔
- B. Backs up data
- C. Updates the image
- D. Monitors CPU only

Explanation: Health checks let an orchestrator or load balancer detect an unhealthy instance and restart it or stop sending it traffic.

Approved by: ______

Correction: ______

## devops-legacy-08

Deployment and configuration · difficulty 1 · independent solve passed

What is a rollback?

- A. Reverting to the previous working version after a bad release ✔
- B. Clearing caches
- C. Scaling up
- D. Rotating logs

Explanation: A rollback returns the system to the last known-good version after a bad release.

Approved by: ______

Correction: ______

## devops-legacy-09

Containers (Docker) · difficulty 1 · independent solve passed

What is the difference between a Docker image and a container?

- A. Images run processes
- B. An image is a template; a container is a running instance of it ✔
- C. None
- D. Containers are stored on Docker Hub

Explanation: An image is a read-only template made of layers; a container is a running (or stopped) instance created from it.

Approved by: ______

Correction: ______

## devops-legacy-12

Deployment and configuration · difficulty 1 · independent solve passed

What does 'least privilege' mean?

- A. Running fewer services
- B. Giving everyone admin rights
- C. Using the cheapest server
- D. Giving each user or service only the permissions it needs ✔

Explanation: Least privilege gives each user, service or token only the permissions required for its task, limiting the damage of a mistake or compromise.

Approved by: ______

Correction: ______

## devops-legacy-13

Containers (Docker) · difficulty 2 · independent solve passed

Why run containers as a non-root user?

- A. Docker requires it
- B. It is faster
- C. It saves disk
- D. It limits the damage if the container is compromised ✔

Explanation: If an attacker compromises a process running as root in a container, they hold far more power, and a container escape would yield root on the host. A non-root user limits that.

Approved by: ______

Correction: ______

## devops-legacy-14

Deployment and configuration · difficulty 1 · independent solve passed

What is a reverse proxy such as Nginx commonly used for?

- A. Writing logs only
- B. Running databases
- C. Terminating TLS, routing and load-balancing requests to backends ✔
- D. Compiling code

Explanation: A reverse proxy sits in front of backend servers to terminate TLS, route by host or path, load-balance and add caching or rate limits.

Approved by: ______

Correction: ______

## devops-legacy-15

Monitoring and logs · difficulty 2 · independent solve passed

What is the purpose of log aggregation?

- A. Testing
- B. Compressing code
- C. Collecting logs from many services in one place to search and alert ✔
- D. Deleting logs

Explanation: Log aggregation ships logs from all instances to a central system so they can be searched, correlated and used for alerts.

Approved by: ______

Correction: ______

## devops-legacy-16

Deployment and configuration · difficulty 2 · independent solve passed

What is infrastructure as code?

- A. Hard-coding IP addresses
- B. Managing infrastructure through versioned configuration files ✔
- C. A programming language
- D. Writing code on servers

Explanation: Infrastructure as code describes servers, networks and services in versioned files, so environments are reviewed, repeatable and recreated automatically.

Approved by: ______

Correction: ______

## devops-containers-01

Containers (Docker) · difficulty 2 · independent solve passed

Builds are slow: every small source change reinstalls all dependencies. What is the best fix for this Dockerfile?

```
FROM node:20-slim
WORKDIR /app
COPY . .
RUN npm ci
CMD ["node", "server.js"]
```

- A. Copy package.json and the lock file and run npm ci before `COPY . .` ✔
- B. Replace `npm ci` with `npm install`
- C. Move the CMD instruction above the COPY instruction
- D. Change the base image tag to node:latest

Explanation: Docker caches each layer and invalidates it, and every layer after it, when its inputs change. With `COPY . .` first, any source edit busts the cache for npm ci. Copying only the dependency manifests first keeps the install layer cached until they change.

Approved by: ______

Correction: ______

## devops-containers-02

Containers (Docker) · difficulty 3 · independent solve passed

Given this Dockerfile, which command does `docker run myimage --port 9000` execute inside the container?

```
FROM python:3.12-slim
WORKDIR /app
COPY . .
ENTRYPOINT ["python", "app.py"]
CMD ["--port", "8000"]
```

- A. python app.py --port 8000 --port 9000
- B. python app.py --port 9000 ✔
- C. --port 9000
- D. python app.py

Explanation: ENTRYPOINT is the fixed executable and CMD supplies default arguments. Arguments given after the image name replace CMD entirely but are appended to ENTRYPOINT, giving `python app.py --port 9000`.

Approved by: ______

Correction: ______

## devops-containers-03

Containers (Docker) · difficulty 3 · independent solve passed

The image builds, but the container exits with `Error: Cannot find module 'express'`. What is the cause?

```
FROM node:20 AS build
WORKDIR /app
COPY . .
RUN npm ci && npm run build

FROM node:20-slim
WORKDIR /app
COPY --from=build /app/dist ./dist
CMD ["node", "dist/server.js"]
```

- A. The node:20-slim image does not include the express package
- B. The CMD instruction must use shell form for modules to load
- C. Only /app/dist was copied from the build stage, so node_modules is not in the final image ✔
- D. The build stage must be the last stage for COPY --from to work

Explanation: Each stage starts from a fresh filesystem; only what is explicitly copied with COPY --from reaches the final image. node_modules stayed in the build stage. Install production dependencies in the final stage or copy node_modules across.

Approved by: ______

Correction: ______

## devops-ci-cd-01

CI/CD · difficulty 2 · independent solve passed

A developer opens a pull request from a feature branch, but no CI run starts. What is the most likely reason?

```
on:
  push:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci && npm test
```

- A. ubuntu-latest runners cannot run npm
- B. actions/checkout needs a personal access token
- C. npm ci cannot run for pull requests
- D. The workflow only triggers on pushes to main; it has no pull_request trigger ✔

Explanation: A workflow runs only for the events listed under `on`. Here that is a push to main, so a feature-branch pull request triggers nothing. Add `pull_request:` (optionally restricted to main) to test changes before they merge.

Approved by: ______

Correction: ______

## devops-ci-cd-02

CI/CD · difficulty 2 · independent solve passed

Why is it good practice to build the Docker image once in the pipeline and promote that same image from staging to production?

- A. What was tested in staging is exactly the artifact that ships ✔
- B. Rebuilding for each environment is not allowed by Docker
- C. Production images must be smaller than staging images
- D. It removes the need for environment-specific configuration

Explanation: Rebuilding per environment can pick up different dependencies or base-image changes, so production could differ from what was tested. Promoting one immutable artifact keeps them identical; environment differences are injected through configuration.

Approved by: ______

Correction: ______

## devops-ci-cd-03

CI/CD · difficulty 2 · execution check passed

A pipeline step runs this shell script with `set -e`. What does it print?

```
set -e
false || true
echo "deploying"
```

- A. Nothing, because false stops the script
- B. deploying ✔
- C. Nothing, because set -e rejects `|| true`
- D. false

Explanation: `false || true` is a list whose status is the status of `true`, so the command counts as handled and set -e does not exit. The script continues and prints deploying. This is why appending `|| true` to a test command hides failures in CI.

Approved by: ______

Correction: ______

## devops-ci-cd-04

CI/CD · difficulty 3 · execution check passed

A CI step runs the script below with plain bash (no pipefail option), where `false` stands for a failing build. What happens?

```
set -e
false | cat
echo "deploying"
```

- A. It stops before printing, because set -e fails on any command in a pipeline
- B. It prints deploying, because set -e only applies to the first line
- C. It prints deploying, because a pipeline's status is that of its last command ✔
- D. It stops before printing, because cat fails on empty input

Explanation: Without `set -o pipefail`, a pipeline's exit status is that of its last command (cat, which succeeds), so set -e does not stop the script even though the first command failed. This is how a failing build piped into tee or cat is silently ignored.

Approved by: ______

Correction: ______

## devops-ci-cd-05

CI/CD · difficulty 3 · independent solve passed

During a zero-downtime rolling deploy, a release adds a NOT NULL column without a default. Old instances, still serving traffic, start failing their inserts. Which approach avoids this?

- A. Run the migration only after every instance runs the new code
- B. Take the whole application offline during every migration
- C. Stop running migrations in the deploy pipeline
- D. Make migrations backward compatible: add the column as nullable, deploy code that writes it, backfill, then add the constraint later ✔

Explanation: During a rolling deploy old and new code run against the same database, so each schema change must work for both versions. The expand-and-contract pattern splits the change into compatible steps. Offline migrations would cause downtime, and new code usually needs the new column.

Approved by: ______

Correction: ______

## devops-deployment-config-01

Deployment and configuration · difficulty 3 · independent solve passed

With this Compose file the api container sometimes crashes at startup with `connection refused` to the database. What is the cause and fix?

```
services:
  api:
    build: .
    depends_on:
      - db
  db:
    image: postgres:16
```

- A. depends_on only waits for the db container to start, not for PostgreSQL to accept connections; add a healthcheck and condition: service_healthy ✔
- B. depends_on must list the image name rather than the service name
- C. The api service needs a ports mapping before it can reach db
- D. Compose starts services in alphabetical order, so db starts after api

Explanation: By default depends_on only orders container start. The database process needs a few seconds to accept connections. Define a healthcheck on db (for example pg_isready) and use `condition: service_healthy`, or make the app retry its connection.

Approved by: ______

Correction: ______

## devops-monitoring-logs-01

Monitoring and logs · difficulty 1 · independent solve passed

Why do teams write application logs as structured JSON instead of free-form text?

- A. JSON log lines are smaller than plain text
- B. Each field can be searched, filtered and aggregated by log tools ✔
- C. Structured logs do not need timestamps
- D. JSON logs are encrypted automatically

Explanation: Structured logs carry named fields such as level, request_id and duration_ms, so a log platform can filter and aggregate on them without fragile text parsing. They are not smaller, and neither encrypted nor timestamp-free.

Approved by: ______

Correction: ______

## devops-monitoring-logs-02

Monitoring and logs · difficulty 2 · independent solve passed

The on-call engineer receives about 200 alerts a night, most of them harmless, and has started ignoring them. What is the best fix?

- A. Send every alert to more people on the team
- B. Alert on every error line written to the log
- C. Alert on user-facing symptoms such as error rate and latency, and remove or tune noisy alerts ✔
- D. Mute all alerts between midnight and 6 a.m.

Explanation: Alert fatigue makes real incidents get missed. Alerts should be actionable and tied to what users experience, with thresholds tuned so each one needs a human. Paging more people, alerting on every log line or muting nights do not improve signal quality.

Approved by: ______

Correction: ______

## devops-monitoring-logs-03

Monitoring and logs · difficulty 2 · independent solve passed

A request passes through five microservices and is slow. What lets you follow that single request across all of them?

- A. Increasing the log level to DEBUG in each service
- B. Comparing the average CPU use of each service
- C. Restarting the services one at a time
- D. A trace or correlation ID passed along in headers and included in every log line ✔

Explanation: Distributed tracing assigns an ID to the incoming request and propagates it to downstream calls (for example the traceparent header), so logs and spans from every service can be joined. Log verbosity and CPU averages cannot tie events to one request.

Approved by: ______

Correction: ______

## devops-monitoring-logs-04

Monitoring and logs · difficulty 3 · independent solve passed

Dashboards show an average API latency of 120 ms, yet some customers report that the app often hangs for several seconds. Which metric should you look at?

- A. The 99th-percentile latency ✔
- B. The average CPU utilisation
- C. The total number of requests
- D. The minimum latency

Explanation: Averages hide the slow tail: a few very slow requests barely move the mean. High percentiles such as p95 or p99 show what the slowest requests experience, which is what these customers are seeing.

Approved by: ______

Correction: ______

## devops-monitoring-logs-05

Monitoring and logs · difficulty 3 · independent solve passed

A service exports the counter `http_requests_total`. Which PromQL expression gives the average requests per second over the last 5 minutes?

- A. http_requests_total / 300
- B. rate(http_requests_total[5m]) ✔
- C. avg(http_requests_total)
- D. max_over_time(http_requests_total[5m])

Explanation: A counter only ever increases (until a restart), so its raw value is a total since start. rate() computes the per-second increase over the window and handles counter resets. Dividing the raw total or taking max or avg does not give a rate.

Approved by: ______

Correction: ______

## devops-deployment-config-02

Deployment and configuration · difficulty 2 · independent solve passed

A team wants to release a risky change but limit the damage if it is faulty. They route 5% of live traffic to the new version first and watch the error rate. What is this strategy called?

- A. A blue-green deployment
- B. A rolling restart of all instances
- C. A canary release ✔
- D. A staging environment test

Explanation: A canary release exposes the new version to a small share of real traffic and compares its health with the old version before widening the rollout. Blue-green switches all traffic at once, and staging tests use no live traffic.

Approved by: ______

Correction: ______
