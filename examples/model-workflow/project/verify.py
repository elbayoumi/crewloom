import json,pathlib,subprocess,sys
result=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests'],capture_output=True,text=True)
pathlib.Path('artifacts').mkdir(exist_ok=True)
pathlib.Path('artifacts/verification.json').write_text(json.dumps({'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr}))
raise SystemExit(result.returncode)
