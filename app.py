from flask import Flask
from pose.routes import pose_bp
from audio.routes import audio_bp
from evaluation.routes import eval_bp
from auth.routes import auth_bp
from orchestrator.routes import orchestrator_bp
import logging
import os

def create_app() -> Flask:
    """
    Flask Application Factory.
    Registers all pipeline blueprints.
    """
    app = Flask(__name__)
    
    # Configure JSON to preserve Unicode (fix \u2014 etc)
    app.json.ensure_ascii = False
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Register Blueprints
    app.register_blueprint(pose_bp)
    app.register_blueprint(audio_bp)
    app.register_blueprint(eval_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(orchestrator_bp)
    
    # Create temp directory if it doesn't exist
    tmp_dir = os.path.join(os.getcwd(), "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    
    @app.route("/health")
    def health():
        return {"status": "healthy", "pipelines": ["pose", "audio", "evaluation", "auth", "orchestrator"]}, 200

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)
