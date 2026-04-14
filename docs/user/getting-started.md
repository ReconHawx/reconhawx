# ReconHawx User Getting Started

This guide helps a new user go from first login to first useful recon results in the UI.

If you still need to install ReconHawx, start with:

- [Installation on Kubernetes](../install-on-kubernetes.md)
- [Installation on Minikube](../install-on-minikube.md)

## Core concepts

- **Program**: The target you are monitoring (with in-scope and out-of-scope rules).
- **Workflow**: A reusable chain of recon tasks.
- **Single task run**: A one-off execution of one task, useful for testing.
- **Assets**: Discovered data such as subdomains, IPs, URLs, services, and certificates.

## 1) Create a program and set scope

1. In the top navigation bar, open **Programs**.
2. Select **Create Program** and enter a clear program name.
3. After creation, ReconHawx redirects you to the program detail page.
4. Define your initial scope:
   - Add your known in-scope roots (for example apex domains and CIDRs).
   - Add out-of-scope patterns for known exclusions.
   - Save your program settings.
5. Validate the scope quickly:
   - In-scope entries should represent what you want recon tasks to discover.
   - Out-of-scope entries should remove noisy or unauthorized targets.

What success looks like:
- The program is saved and visible in your Programs list.
- Scope rules are set and reflect your approved target boundaries.

## 2) Create your first workflow

1. In the top navigation bar, open **Workflows**, then select **Create workflow**.
2. Add tasks in the order you want to execute them.
3. Give the workflow a descriptive name (for example, `initial-enumeration`).
4. Save the workflow definition.
5. Re-open it once to confirm tasks, order, and parameters are correct.

Starter guidance:
- Begin with a short workflow focused on discovery and validation.
- Keep your first workflow small so failures are faster to debug.

What success looks like:
- The workflow appears in your workflow list.
- You can open it in edit mode and see the expected tasks and settings.

## 3) Run a single task

Single task runs are best when you want to test one task quickly before running full workflows.

1. In the top navigation bar, open **Workflows**.
2. Launch **Single Task** from the workflow page.
3. Select a task and provide required input values (for example, program/scope-related target input).
4. Start the run.
5. Open **Workflow Status** to monitor execution and inspect logs.

When to use single task vs workflow:
- Use **single task** for fast validation and troubleshooting.
- Use a **saved workflow** for repeatable multi-step runs.

What success looks like:
- The task run completes (or fails with clear logs you can act on).
- Output artifacts can be traced to asset views or execution logs.

## 4) Explore assets

After runs complete, verify what ReconHawx discovered.

Use the asset pages:
- Subdomains: **Assets -> Subdomains**
- Apex domains: **Assets -> Apex Domains**
- IPs: **Assets -> IPs**
- URLs: **Assets -> URLs**
- Services: **Assets -> Services**
- Certificates: **Assets -> Certificates**

Suggested review loop:
1. Open one asset table and filter for your program scope.
2. Drill into a few detail pages to confirm quality and context.
3. Note missing expected targets or noisy results.
4. Refine program scope and/or workflow task configuration.
5. Re-run a single task or workflow and compare results.

What success looks like:
- You can see discovered assets aligned with your scope.
- You have an iterative loop: scope/workflow update -> run -> asset review.

## Suggested first-day routine

1. Create one program with clear scope boundaries.
2. Save one small starter workflow.
3. Run one single task to validate inputs and outputs.
4. Run the full workflow.
5. Review assets and adjust scope/workflow for the next run.

## Related documentation

- [Programs Guide](programs.md)
- [Workflows Guide](workflows.md)
- [Installation on Kubernetes](../install-on-kubernetes.md)
- [Installation on Minikube](../install-on-minikube.md)
- [Upgrading ReconHawx on Kubernetes](../update-reconhawx.md)
- [Uninstalling ReconHawx](../uninstall-reconhawx.md)
