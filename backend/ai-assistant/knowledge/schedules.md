---
id: schedules
title: Schedules
route: "/scheduled-jobs"
group: Build
audience: user
source: docs
tags: [docs, build]
---

## Schedules

One table of every cron schedule attached to your agents and workflows.

Schedules are created inside the Agent builder or Workflow builder — the Schedules page is the read view. It lists each schedule with the parsed frequency and its timezone, the next and last run, and an active/paused badge. Times are shown in each schedule’s own timezone.

1. Add a schedule card to an agent, or a schedule node to a workflow, and set the frequency, time, day and timezone.
2. Save the agent or workflow. The schedule is mirrored into the scheduler registry and appears on the Schedules page.
3. Open Schedules to review all schedules. Enabled ones are sorted first, soonest to fire, then alphabetically.
4. Use the actions menu on a row to Edit schedule (opens the builder) or Open in chat.

## Schedules

- The scheduler checks for due schedules every minute and runs the target as the platform service.
- Each scheduled run creates a conversation of kind “run”, so it is a readable transcript in Chat.
- Cron is parsed timezone-aware, including daylight-saving transitions.
- Pausing is done by disabling the schedule in the builder; a schedule with an empty cron is not shown at all.

**Timezone comes from Settings** — Your Settings timezone pre-fills schedule configuration, and each schedule stores its own timezone so a scheduled job always fires at the intended local time.
