import os, tempfile, unittest
from detectors.stack_detector import detect_stack
from dockerfile_builder import build_dockerfile
from source_patcher import patch_source_host_binding
from security import scan_secrets

class CoreTests(unittest.TestCase):
    def test_flask_detect_and_template_binds_all_interfaces(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d,"app.py"),"w").write("from flask import Flask\napp=Flask(__name__)\n")
            open(os.path.join(d,"requirements.txt"),"w").write("flask\n")
            info=detect_stack(d)
            self.assertEqual(info.stack,"flask")
            dockerfile=build_dockerfile(info)
            self.assertIn("0.0.0.0:5000",dockerfile)
            self.assertIn("app:app",dockerfile)
            self.assertIn("gunicorn",dockerfile)
    def test_fastapi_explicit_host(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d,"main.py"),"w").write("from fastapi import FastAPI\napp=FastAPI()")
            open(os.path.join(d,"requirements.txt"),"w").write("fastapi\n")
            info=detect_stack(d)
            self.assertEqual(info.stack,"fastapi")
            self.assertIn("--host 0.0.0.0", info.run_cmd)
    def test_java_template_exists(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d,"pom.xml"),"w").write("<project/>")
            info=detect_stack(d)
            self.assertEqual(info.stack,"java-maven")
            self.assertIn("mvn -B -DskipTests package",build_dockerfile(info))
    def test_source_patch_flask_binding(self):
        with tempfile.TemporaryDirectory() as d:
            path=os.path.join(d,"app.py")
            open(path,"w").write("from flask import Flask\napp=Flask(__name__)\napp.run(debug=True)\n")
            result=patch_source_host_binding(d,"flask",5000)
            self.assertTrue(result.changed)
            content=open(path).read()
            self.assertIn('host="0.0.0.0"',content)
            self.assertIn('os.environ.get("PORT"',content)
    def test_secret_scanner(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d,".env"),"w").write("SECRET=abc")
            open(os.path.join(d,"config.py"),"w").write('api_key = "sk-123456789012345678901234"')
            findings=scan_secrets(d)
            self.assertTrue(findings)
if __name__ == "__main__": unittest.main()
