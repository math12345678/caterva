# Assistant fixtures

Real API responses of the studio server's `/api/assistant/*` routes, for the page's component tests. Each file is
`{request, status, body}` as the server answered through `App.dispatch`, captured by
`caterva/tests/capture_assistant_ui_fixtures.py` over a REAL captured compose result (LDH with a competitive
inhibitor, analysed). The model behind them is a fake transport returning hand-written replies, so the files show
what the server does with a reply (accepts it, rejects it, falls back to the engine's text), not what a real model
would write. The replies are named in the file names (`explain-accepted`, `explain-rejected`, ...). Do not edit by
hand; run the script again.
