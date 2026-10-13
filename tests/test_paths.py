"""Windows <-> Linux/Mac のパス変換テスト: python3 tests/test_paths.py"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "plugins/session-share/scripts"))
from ccshare import PathMapper, encode_project_dir

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
print("OK")
