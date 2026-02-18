from flask import Blueprint

# Create a Blueprint for the student dashboard
support_bp = Blueprint('support', __name__)

# Define a simple route for the student dashboard
@support_bp.route('/')
def support():
    return "Welcome to the Student Dashboard!"