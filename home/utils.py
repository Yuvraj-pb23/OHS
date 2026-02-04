import os
from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML

def generate_certificate(user, course_type="POSH"):
    """
    Generates a PDF certificate for the given user and course type.
    """
    # 1. Determine Template Image
    # TODO: Add logic for POSH template when available. For now, using POCSO for both.
    template_name = "CERTIFICATE TEMPLATE FOR POCSO TRAINING.png"
    
    # Construct absolute path to the image for WeasyPrint
    image_path = os.path.join(settings.MEDIA_ROOT, template_name)
    if not os.path.exists(image_path):
        # Fallback or error handling
        print(f"ERROR: Certificate template not found at {image_path}")
        return None

    # 2. Prepare Context
    context = {
        "candidate_name": f"{user.first_name} {user.last_name}".strip() or user.username,
        "course_type": course_type,
        "completion_date": timezone.now().strftime("%d %B %Y"), # e.g. 14 February 2026
        "image_path": f"file://{image_path}", # WeasyPrint needs file:// protocol for local images
    }

    # 3. Generate HTML
    # Inline CSS for pixel-perfect positioning (based on user requirement)
    html_string = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            @page {{
                size: 297mm 210mm; /* A4 Landscape */
                margin: 0;
            }}
            body {{
                margin: 0;
                padding: 0;
                width: 297mm;
                height: 210mm;
                background-image: url('{context['image_path']}');
                background-size: cover;
                background-repeat: no-repeat;
                font-family: 'Helvetica', 'Arial', sans-serif; /* Setup appropriate font */
                position: relative;
                color: #333; 
            }}
            .candidate-name {{
                position: absolute;
                top: 45%; /* Adjust based on template visual */
                left: 0;
                width: 100%;
                text-align: center;
                font-size: 32pt;
                font-weight: bold;
                color: #000;
                text-transform: uppercase;
            }}
            .course-type {{
                position: absolute;
                top: 55%; /* Adjust based on template visual */
                left: 0;
                width: 100%;
                text-align: center;
                font-size: 18pt;
                color: #555;
            }}
            .date {{
                position: absolute;
                bottom: 22%; /* Adjust based on template visual */
                left: 24%; /* Adjust */
                font-size: 14pt;
                font-weight: bold;
            }}
            /* Debug helper to find positions - remove in prod */
            /* .grid {{ position: absolute; top:0; left:0; width:100%; height:100%; grid-template-columns: repeat(10, 1fr); display: grid; opacity: 0.2; pointer-events: none; }} */
        </style>
    </head>
    <body>
        <div class="candidate-name">{context['candidate_name']}</div>
        <div class="course-type">Successfully completed the <b>{context['course_type']}</b> Training</div>
        <div class="date">{context['completion_date']}</div>
    </body>
    </html>
    """

    # 4. Convert to PDF
    pdf_file = HTML(string=html_string).write_pdf()
    
    return pdf_file
