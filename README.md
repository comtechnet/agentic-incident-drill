# agentic-incident-drill

A sandbox for rehearsing AI-assisted incident response end to end: alert, diagnosis against the release diff, a human approval gate, rollback, recovery check and a written postmortem.

The target service, `clinic-hours`, answers "which clinics in this town are open, and when?" for **Larkspur County, a fictional county**. All data is synthetic: fictional places and opening hours only. There are no people or patient records anywhere in this repository, and none should ever be added.

## Run locally

```
npm test
npm start            # http://localhost:8070
```

Endpoints: `/clinics?town=Fernhill`, `/towns`, `/healthz`, `/metrics`.

## Releases

Each release is a git tag (`v1.3`, `v1.4`, ...). The `prod` tag marks what is deployed; rolling back means moving `prod` to an earlier release.
