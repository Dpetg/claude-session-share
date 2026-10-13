"""Windows <-> Linux/Mac のパス変換テスト: python3 tests/test_paths.py"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "plugins/session-share/scripts"))
from ccshare import PathMapper, encode_project_dir, normalize_remote, SecretFilter

win = PathMapper(r"C:\Users\shota\src\demo", r"C:\Users\shota", windows=True)
lin = PathMapper("/home/shota/work/demo", "/home/shota", windows=False)
mac = PathMapper("/Users/shota/dev/demo", "/Users/shota", windows=False)

cases = [
    (r"C:\Users\shota\src\demo\a.py", "{{CCSHARE_PROJECT}}\\a.py"),
    ("c:/users/shota/src/demo/b.py", "{{CCSHARE_PROJECT}}/b.py"),
    (r"C:\Users\shota\src\demo2\x", "{{CCSHARE_HOME}}\\src\\demo2\\x"),
    (r"cd C:\Users\shota\src\demo && type C:\Users\shota\.claude\settings.json",
     "cd {{CCSHARE_PROJECT}} && type {{CCSHARE_HOME}}\\.claude\\settings.json"),
]
for src, want in cases:
    got = win.to_store(src)
    assert got == want, (src, got)

stored = win.to_store(r"C:\Users\shota\src\demo\pkg\mod.py")
assert lin.to_local(stored) == "/home/shota/work/demo/pkg/mod.py", lin.to_local(stored)
assert win.to_local(lin.to_store("/home/shota/work/demo/pkg/mod.py")) == r"C:\Users\shota\src\demo/pkg/mod.py"
assert mac.to_local(lin.to_store("/home/shota/.claude/x")) == "/Users/shota/.claude/x"
assert lin.to_store("/home/shota/work/demo-old/x") == "{{CCSHARE_HOME}}/work/demo-old/x"
obj = win.walk({"cwd": "{{CCSHARE_PROJECT}}/sub"}, win.to_local)
assert obj["cwd"] == r"C:\Users\shota\src\demo\sub", obj
assert encode_project_dir(r"C:\Users\shota\src\demo") == "C--Users-shota-src-demo"
# macOS の /var -> /private/var のように、同じプロジェクトを別の表記で記録した会話も置き換える
mac2 = PathMapper("/private/var/u/demo", "/Users/u", windows=False, aliases=["/var/u/demo"])
assert mac2.to_store("/var/u/demo/a.py") == "{{CCSHARE_PROJECT}}/a.py"
assert mac2.to_store("/private/var/u/demo/a.py") == "{{CCSHARE_PROJECT}}/a.py"
# 同じリポジトリなら SSH / HTTPS・ポートの違いによらず同じプロジェクトとして扱う
same = [
    "git@git.example.com:me/app.git",
    "ssh://git@git.example.com:2222/me/app.git",
    "https://git.example.com/me/app",
    "https://user@git.example.com:8443/me/app.git/",
]
assert {normalize_remote(u) for u in same} == {"git.example.com/me/app"}, [normalize_remote(u) for u in same]
assert normalize_remote("git@github.com:Dpetg/Demo.git") == "github.com/dpetg/demo"
assert normalize_remote("me@nas:/srv/git/app.git") == "nas/srv/git/app"
assert normalize_remote("ssh://nas/~me/app.git") == "nas/app"
assert normalize_remote(r"C:\git\app.git") == "local/c:/git/app"
# 秘密情報の検出: 本物らしい値は伏せ、コードや説明文は残す
f = SecretFilter("mask")
assert "REDACTED" in f("export OPENAI_API_KEY=sk-proj-" + "Ab3" * 15)
assert "REDACTED" in f('password = "hunter2hunter2x"')
assert f("const apiKey = process.env.API_KEY_VALUE;") == "const apiKey = process.env.API_KEY_VALUE;"
assert f("set ACCESS_TOKEN=proxy-injected-value") == "set ACCESS_TOKEN=proxy-injected-value"
assert f("token: ${{ secrets.GITHUB_TOKEN }}") == "token: ${{ secrets.GITHUB_TOKEN }}"
assert "REDACTED" in f("-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----")
print("OK")
