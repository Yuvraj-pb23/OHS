import os
from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
import os
from weasyprint import HTML

def generate_certificate(user, course_type="POSH"):
    """
    Generates a PDF certificate for the given user and course type.
    """
    # 1. Determine Template Image
    if course_type == "POSH":
        template_name = "Certificate/POSH CERT.png"
    else:
        template_name = "Certificate/POCSO CERT.png"
    
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
        "completion_date": timezone.now().strftime("%d/%m/%Y"), # e.g. 05/02/2026
        "image_path": f"file://{image_path}", # WeasyPrint needs file:// protocol for local images
    }

    # Determine date position
    date_left = "35.5%" if course_type == "POSH" else "37%"

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
                top: 47%; /* Lowered as requested */
                left: 0;
                width: 100%;
                text-align: center;
                font-size: 36pt;
                font-weight: bold;
                color: #000;
                text-transform: uppercase;
            }}
            .date {{
                position: absolute;
                bottom: 33%; 
                left: {date_left};   /* Dynamic positioning */
                font-size: 16pt;
                font-weight: bold;
                color: #000;
            }}
            /* Debug helper to find positions - remove in prod */
            /* .grid {{ position: absolute; top:0; left:0; width:100%; height:100%; grid-template-columns: repeat(10, 1fr); display: grid; opacity: 0.2; pointer-events: none; }} */
        </style>
    </head>
    <body>
        <div class="candidate-name">{context['candidate_name']}</div>
        <div class="date">{context['completion_date']}</div>
    </body>
    </html>
    """

    # 4. Convert to PDF
    pdf_file = HTML(string=html_string).write_pdf()
    
    return pdf_file


def get_posh_billing_data(registration):
    """Refactored helper to calculate POSH billing context without HTTP request"""
    from .models import POSHPricingConfig
    
    config = POSHPricingConfig.objects.filter(is_active=True).order_by('-updated_at').first()
    if not config:
        config = POSHPricingConfig()
        
    emp_count = registration.employee_count
    
    # 1. Determine Tier (t0 to t4)
    if emp_count <= config.price_tier_0_max:
        tier = 't0'
        per_employee_rate = config.price_tier_0_rate
    elif emp_count <= config.price_tier_1_max:
        tier = 't1'
        per_employee_rate = config.price_tier_1_rate
    elif emp_count <= config.price_tier_2_max:
        tier = 't2'
        per_employee_rate = config.price_tier_2_rate
    elif emp_count <= config.price_tier_3_max:
        tier = 't3'
        per_employee_rate = config.price_tier_3_rate
    else:
        tier = 't4'
        per_employee_rate = config.price_tier_4_rate

    # 2. Build Add-on Fees
    addon_fees = []
    training_cost = float(emp_count * per_employee_rate)
    
    # 2a. Base Subscription
    addon_fees.append({
        'label': f'POSH Act Compliance ({emp_count} Employees)',
        'amount': training_cost,
        'points': ['Awareness Education', 'Certification Support', 'Compliance Records']
    })
    
    # 2b. Policy Drafting
    if not registration.has_posh_policy:
        fee = float(getattr(config, f'fee_no_posh_policy_{tier}', 0))
        addon_fees.append({
            'label': 'POSH Protection Policy Drafting', 
            'amount': fee,
            'points': ['Full Policy Drafting', 'Legal Verification', 'Final Document Provision']
        })
            
    # 2c. IC Formation
    if not registration.has_ic:
        fee = float(getattr(config, f'fee_no_ic_{tier}', 0))
        addon_fees.append({
            'label': 'Internal Committee (IC) Formation', 
            'amount': fee,
            'points': ['Member Appointment', 'Roles & Responsibilities', 'Statutory Documentation']
        })
            
    # 2d. IC Training (Simplified for PDF)
    if registration.require_ic_training:
        req_mode = registration.requested_ic_training_mode
        if req_mode == 'ONLINE':
            rate_field = 'fee_ic_requested_online'
            display_mode = 'Online'
        elif req_mode == 'EXPERT_LED':
            req_type = registration.requested_expert_led_type
            if req_type == 'PHYSICAL':
                rate_field = 'fee_ic_requested_physical'
                display_mode = 'Physical'
            else:
                rate_field = 'fee_ic_requested_virtual'
                display_mode = 'Virtual'
        else:
            rate_field = 'fee_ic_history_other'
            display_mode = 'Standard'

        fee = float(getattr(config, f'{rate_field}_{tier}', 0))
        addon_fees.append({
            'label': f'IC Specialized Training ({display_mode})', 
            'amount': fee,
            'points': ['Expert-Led Session', 'Case Study Analysis', 'Legal Framework']
        })

    # 2e. External Member Support
    if registration.require_external_member_support:
        fee = float(getattr(config, f'fee_no_external_member_{tier}', 0))
        addon_fees.append({
            'label': 'External Member Matchmaking', 
            'amount': fee,
            'points': ['Authorized Expert Search', 'Statutory Compliance', 'Yearly Support']
        })
            
    # 2f. Statutory Portal (SHe Box)
    if not registration.she_box_registered or registration.require_nodal_officer_support:
        fee = float(getattr(config, f'fee_not_she_box_{tier}', 0))
        addon_fees.append({
            'label': 'Statutory Portal Compliance (SHe Box)', 
            'amount': fee,
            'points': ['Portal Registration', 'Digital Onboarding', 'Compliance Maintenance']
        })

    subtotal = sum(item['amount'] for item in addon_fees)
    gst_rate = float(config.gst_percentage) / 100
    
    return {
        "addon_fees": addon_fees,
        "subtotal": subtotal,
        "gst_percentage": config.gst_percentage,
        "gst_amount": subtotal * gst_rate,
        "total_amount": subtotal * (1 + gst_rate),
        "training_total": training_cost,
        "total_add_ons": subtotal - training_cost,
    }

def get_pocso_billing_data(registration):
    """Refactored helper to calculate POCSO billing context without HTTP request"""
    from .models import POCSOPricingConfig
    config = POCSOPricingConfig.objects.filter(is_active=True).order_by('-updated_at').first()
    if not config: config = POCSOPricingConfig()

    gst_pct = float(config.gst_percentage)
    addon_fees = []
    
    if not registration.has_policy:
        addon_fees.append({
            'label': 'Child Protection Policy Drafting', 
            'amount': float(config.fee_no_policy),
            'points': ['Drafting & Customization', 'Statutory Review', 'Institutional Integration']
        })
    if not registration.has_committee:
        addon_fees.append({
            'label': 'Child Safety Committee Formation', 
            'amount': float(config.fee_no_committee),
            'points': ['Member Selection Support', 'Appointment Letters', 'Statutory Documentation']
        })
    
    if not registration.teaching_staff_trained:
        mode = (registration.teaching_training_mode or 'ONLINE').upper()
        rate_attr = f'teacher_rate_{mode.lower().replace("_", "")}'
        rate = float(getattr(config, rate_attr, config.teacher_rate_online))
        
        if mode == 'E_LEARNING':
            amount = registration.teachers_count * rate
            label = f'POCSO Awareness: Teaching Staff (Per Head x {registration.teachers_count})'
        else:
            amount = rate
            label = f'POCSO Awareness: Teaching Staff ({mode.title()} - Fixed Fee)'
            
        addon_fees.append({
            'label': label, 
            'amount': amount,
            'points': ['Educational Resource Access', 'Certification Support', 'Compliance Reporting']
        })
    
    if not registration.non_teaching_staff_trained:
        mode = (registration.non_teaching_training_mode or 'ONLINE').upper()
        rate_attr = f'staff_rate_{mode.lower().replace("_", "")}'
        rate = float(getattr(config, rate_attr, config.staff_rate_online))
        
        if mode == 'E_LEARNING':
            amount = registration.non_teaching_staff_count * rate
            label = f'POCSO Awareness: Non-Teaching Staff (Per Head x {registration.non_teaching_staff_count})'
        else:
            amount = rate
            label = f'POCSO Awareness: Non-Teaching Staff ({mode.title()} - Fixed Fee)'
            
        addon_fees.append({
            'label': label, 
            'amount': amount,
            'points': ['Educational Resource Access', 'Certification Support', 'Compliance Reporting']
        })
        
    student_workshop_total = 0
    if not registration.students_trained:
        student_workshop_total = registration.students_count * float(config.student_rate)
        addon_fees.append({
            'label': f'Student Body Safety Workshop', 
            'amount': student_workshop_total,
            'points': ['Student Outreach', 'Safety Awareness Curriculum', 'Institutional Safety Audit']
        })

    subtotal = sum(f['amount'] for f in addon_fees)
    gst_amount = subtotal * (gst_pct / 100.0)

    return {
        "addon_fees": addon_fees,
        "subtotal": subtotal,
        "gst_percentage": gst_pct,
        "gst_amount": gst_amount,
        "total_amount": subtotal + gst_amount,
        "flat_fees_total": subtotal - student_workshop_total,
        "student_workshop_total": student_workshop_total,
    }

def generate_proforma_invoice_pdf(registration, registration_type='POSH', tier_key=None):
    """Generates a Proforma Invoice PDF using WeasyPrint"""
    if registration_type == 'POSH':
        billing_data = get_posh_billing_data(registration)
    else:
        billing_data = get_pocso_billing_data(registration)
        
    # Calculate tiered totals (matching logic in views.py)
    total_amount = billing_data['total_amount']
    
    context = {
        'registration': registration,
        'billing_data': billing_data,
        'registration_type': registration_type,
        'tier_key': tier_key,
        'date': timezone.now().strftime("%d %b %Y"),
        'invoice_no': f"PRO-{registration_type[:3]}-{registration.id:05d}",
        'total_tier_1': total_amount * 0.8,
        'total_tier_2': total_amount * 0.9,
        'total_tier_3': total_amount,
        'base_url': settings.BASE_URL if hasattr(settings, 'BASE_URL') else 'https://openhandsolutions.com',
        'logo_path': os.path.join(settings.BASE_DIR, 'static', 'img', 'logo_new.png')
    }
    
    html_string = render_to_string('emails/invoice_pdf.html', context)
    return HTML(string=html_string, base_url=settings.STATIC_ROOT).write_pdf()
