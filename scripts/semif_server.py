"""Local SemIf decision server for the medical-term guard (app/services/term_guard.py).

SemIf (https://github.com/TheoLeeCJ/SemIf-OpenJev) reads typed option probabilities
from an open model on this machine, so transcripts never leave it. It pins its own
torch/transformers/MLX versions, so it runs in its own venv, not the app's:

    git clone https://github.com/TheoLeeCJ/SemIf-OpenJev ../semif
    (cd ../semif && uv venv -p 3.12 && uv pip install -e '.[mlx]')
    ../semif/.venv/bin/python scripts/semif_server.py      # serves 127.0.0.1:8765

POST /decide {"state": ..., "rows": [{"id", "question", "options": [{"id", "description"}]}]}
-> {"model": "...", "answers": {id: {option_id: probability}}}
"""

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

from semif_phase1 import mlx_backend

MODEL = os.getenv("SEMIF_MODEL", "Qwen/Qwen3.5-4B")
REVISION = os.getenv("SEMIF_REVISION", "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a")
BITS = int(os.getenv("SEMIF_BITS", "8"))  # in-memory quantization; 0 = BF16 (~9 GB)
PORT = int(os.getenv("SEMIF_PORT", "8765"))

model, tokenizer, metadata = mlx_backend.load_model(MODEL, REVISION, BITS or None)
NAME = f"{MODEL}@{REVISION[:7]}" + (f"-q{BITS}" if BITS else "")


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/decide":
            return self.send_error(404)
        try:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            rows = [{**row, "state": body["state"]} for row in body["rows"]]
            results, _ = mlx_backend.score_shared(model, tokenizer, rows, metadata)
            answers = {r["id"]: dict(zip(r["option_ids"], r["probabilities"])) for r in results}
            payload, status = {"model": NAME, "answers": answers}, 200
        except (KeyError, TypeError, ValueError) as e:
            payload, status = {"error": str(e)}, 400
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    print(f"SemIf {NAME} on 127.0.0.1:{PORT}", flush=True)
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
