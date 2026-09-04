# Football 1 Web Preview

A zero-backend, responsive interface prototype for the Football 1 research product.

It deliberately separates:

1. football prediction;
2. model disagreement;
3. bookmaker price;
4. break-even probability;
5. Eyes Wide Open decision quality.

The current market values mirror the existing first live-snapshot preview where available. Elo, Poisson and Football 1 values in this interface are explicitly labelled **preview** and are not prospective recommendations.

## Run locally

From the repository root:

```bash
python3 -m http.server 8000 --directory web
```

Then open `http://localhost:8000`.

No package install, API key, server process or LLM call is required for this interface prototype.
