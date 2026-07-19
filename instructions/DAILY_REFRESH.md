# Daily refresh — RETIRED (do nothing)

> **This scheduled-agent refresh is retired as of 2026-07-19.**
>
> The CPL dashboard is now refreshed solely by the GitHub Actions cron
> `.github/workflows/refresh-dashboard.yml` (04:00 UTC), which pulls Meta data
> from the **direct Meta Marketing API** (`meta_direct.py`) — Windsor.ai has been
> removed. Windsor was overstating spend (~15%) and leads (~3x); do NOT reintroduce it.
>
> **If you are the scheduled agent reading this: take no action.** Do not fetch
> from the Windsor.ai MCP, do not write to `data/`, do not commit. The GitHub
> Actions job owns this refresh. Overwriting its output with a Windsor pull would
> revert the dashboard to inflated numbers.
>
> The remaining cleanup task is to disable this scheduled trigger in Bina so this
> file stops being invoked at all.
