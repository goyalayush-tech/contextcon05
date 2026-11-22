# SCOUTSPEND

A research agent that buys Crustdata data under a credit ceiling you can cut mid-run,
and hands back prospect rows where every claim is marked supported, partial or
can't verify, with a dated source.

Status: work in progress (ContextCon 05, BITS Pilani).

## Run the tests (no credits used)

    python3 -I -m unittest discover -s tests -t . -v

## Setup

    cp .env.example .env     # then add CRUSTDATA_API_KEY
