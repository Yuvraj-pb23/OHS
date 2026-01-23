import csv
import io
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db import transaction 
from django.db.models import Q
from django.contrib.auth.decorators import user_passes_test

# Models
# Ensure your User model has 'phone' and 'department' fields if you want to save them to the DB.
from .models import User, SubscriptionPlan, Subscription, Payment, Organization, OrganizationMember
# Ensure this file exists in your app or adjust import accordingly
from .chatbot_logic import predict_answer


# --- 1. LOGIN REDIRECT LOGIC ---
@login_required
def custom_login_redirect(request):
    user = request.user
    
    # 0. SUPERUSER -> Superuser Dashboard
    if user.is_superuser:
        return redirect('superuser_dashboard')
    
    # 1. ADMIN -> Dashboard
    if user.account_type == 'COMPANY_ADMIN':
        return redirect('company_dashboard')
        
    # 2. USER (Employee/Individual) -> Direct to Training Page
    elif user.account_type in ['EMPLOYEE', 'INDIVIDUAL']:
        has_posh = Subscription.objects.filter(
            Q(user=user) | Q(organization__organizationmember__user=user),
            status='ACTIVE',
            plan__type__in=['POSH', 'BOTH']
        ).exists()

        if has_posh:
            return redirect('posh_act_page')

        has_pocso = Subscription.objects.filter(
            Q(user=user) | Q(organization__organizationmember__user=user),
            status='ACTIVE',
            plan__type__in=['POCSO', 'BOTH']
        ).exists()

        if has_pocso:
            return redirect('pocso_act_page')

        return redirect('tutorial') 
        
    return redirect('home')

# --- 2. COMPANY SUBSCRIPTION (SIGNUP) ---
def company_subscription(request, plan_type):
    db_type = 'POSH' if 'POSH' in plan_type else 'POCSO'
    plan = SubscriptionPlan.objects.filter(type=db_type).first()

    if request.method == "POST":
        comp_name = request.POST.get('company_name')
        seats = int(request.POST.get('seats', 10))
        fullname = request.POST.get('fullname')
        email = request.POST.get('email')
        password = request.POST.get('password')

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already registered.")
            return redirect(request.path)

        try:
            with transaction.atomic():
                user = User.objects.create_user(username=email, email=email, password=password)
                user.first_name = fullname
                user.account_type = 'COMPANY_ADMIN'
                user.save()

                org = Organization.objects.create(name=comp_name, owner=user, max_users=seats)
                OrganizationMember.objects.create(organization=org, user=user, role='ADMIN')

                Subscription.objects.create(organization=org, plan=plan, status='ACTIVE', start_date=timezone.now())

            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            return redirect('company_dashboard')
            
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")

    return render(request, 'company_signup.html', {'plan_type': plan_type})

# --- 3. ADD EMPLOYEE (SINGLE) ---
@login_required(login_url='login')
def add_employee(request):
    if request.method == "POST":
        current_user = request.user
        
        membership = OrganizationMember.objects.filter(user=current_user, role='ADMIN').first()
        if not membership:
            messages.error(request, "Unauthorized.")
            return redirect('tutorial')
        
        org = membership.organization
        current_count = OrganizationMember.objects.filter(organization=org).count()
        if current_count >= org.max_users:
            messages.error(request, f"Seat limit reached ({org.max_users}). Upgrade plan to add more.")
            return redirect('company_dashboard')
            
        emp_name = request.POST.get('emp_name')
        emp_email = request.POST.get('emp_email')
        emp_password = request.POST.get('emp_password')
        
        if User.objects.filter(email=emp_email).exists():
            messages.error(request, "User email already exists.")
            return redirect('company_dashboard')

        try:
            with transaction.atomic():
                new_user = User.objects.create_user(username=emp_email, email=emp_email, password=emp_password)
                new_user.first_name = emp_name
                new_user.account_type = 'EMPLOYEE'
                new_user.save()
                
                OrganizationMember.objects.create(organization=org, user=new_user, role='MEMBER')
            
            messages.success(request, f"{emp_name} added successfully!")
        except Exception as e:
            messages.error(request, "Database error.")
            
        return redirect('company_dashboard')
    return redirect('company_dashboard')

# --- 4. COMPANY DASHBOARD ---
@login_required(login_url='login')
def company_dashboard(request):
    user = request.user
    membership = OrganizationMember.objects.filter(user=user, role='ADMIN').first()
    
    if not membership:
        messages.error(request, "Access Denied. Admin only.")
        return redirect('tutorial')
    
    org = membership.organization
    active_sub = Subscription.objects.filter(organization=org, status='ACTIVE').first()
    members = OrganizationMember.objects.filter(organization=org).select_related('user')
    
    # --- DATA CALCULATION FOR HTML ---
    total_employees = members.count()
    seats_remaining = org.max_users - total_employees
    
    # Placeholder Logic: Assuming 0 completed for now
    training_completed = 0 
    training_pending = total_employees - training_completed

    context = {
        'organization': org,
        'active_plan': active_sub,
        'members': members,
        'seats_used': total_employees,
        'seats_remaining': seats_remaining,
        'total_employees': total_employees,
        'training_completed': training_completed,
        'training_pending': training_pending,
    }
    return render(request, 'company_dashboard.html', context)

# --- 5. INDIVIDUAL SUBSCRIPTION ---
def individual_subscription(request, plan_type):
    db_type = 'POSH' if 'POSH' in plan_type else 'POCSO'
    plan = SubscriptionPlan.objects.filter(type=db_type).first()
    
    if request.method == "POST":
        fullname = request.POST.get('fullname')
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username taken.")
            return redirect(request.path)

        try:
            with transaction.atomic():
                user = User.objects.create_user(username=username, email=email, password=password)
                user.first_name = fullname
                user.account_type = 'INDIVIDUAL'
                user.save()

                Subscription.objects.create(user=user, plan=plan, status='ACTIVE', start_date=timezone.now())
                
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            return redirect('posh_act_page')
        except Exception as e:
            messages.error(request, str(e))

    context = {
        'plan_type': plan.name if plan else "Unknown Plan", 
        'price': plan.price if plan else 0
    }
    return render(request, 'subscription_details.html', context)

# --- 6. SECURE TRAINING PAGES ---
@login_required(login_url='login')
def posh_act_page(request):
    user = request.user
    has_access = Subscription.objects.filter(
        Q(user=user) | Q(organization__organizationmember__user=user),
        status='ACTIVE',
        plan__type__in=['POSH', 'BOTH']
    ).exists()

    if not has_access:
        messages.error(request, "Access Denied: Subscription Required.")
        return redirect('tutorial')
    return render(request, 'posh_act_page.html')

@login_required(login_url='login')
def pocso_act_page(request):
    user = request.user
    has_access = Subscription.objects.filter(
        Q(user=user) | Q(organization__organizationmember__user=user),
        status='ACTIVE',
        plan__type__in=['POCSO', 'BOTH']
    ).exists()

    if not has_access:
        messages.error(request, "Access Denied: Subscription Required.")
        return redirect('tutorial')
    return render(request, 'pocso_act_page.html')

# --- 7. STATIC, CHATBOT & INTERMEDIATE PAGES ---
def index(request): return render(request, 'index.html')
def about(request): return render(request, 'about.html')
def resources(request): return render(request, 'resources.html')
def services(request): return render(request, 'services.html')
def blog(request): return render(request, 'blog.html')
def gallery(request): return render(request, 'gallery.html')
def achievements(request): return render(request, 'achievements.html')
def footer(request): return render(request, 'footer.html')
def contact(request): return render(request, 'contact.html')
def posh_T(request): return render(request, 'posh_T.html')
def workplace(request): return render(request, 'workplace.html')
def legal(request): return render(request, 'legal.html')
def blogdata(request): return render(request, 'blogdata.html')
def why_choose_ohs(request): return render(request, 'why_choose_ohs.html')
def posh_compliance(request): return render(request, "posh_compliance.html")
def tutorial_view(request): return render(request, 'tutorial.html')
def posh_assessment(request): return render(request, 'posh_assessment.html')
def pocso_assessment(request): return render(request, 'pocso_assessment.html')

def posh_c(request):
    """
    Renders the intermediate page for POSH Individual course details 
    before the subscription form.
    """
    return render(request, 'posh_c.html')

@csrf_exempt
def chatbot_response(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            msg = data.get('message', '').strip().lower()
            if not msg: return JsonResponse({'error': 'Empty'}, status=400)
            
            if msg in ["bye", "clear"]: return JsonResponse({"response": "Goodbye!", 'reset': True})
            if "hello" in msg: return JsonResponse({'response': "Hi! Ask me about OHS."})
            
            ml_resp = predict_answer(msg)
            return JsonResponse({'response': ml_resp})
        except:
            return JsonResponse({'error': 'Error'}, status=500)
    return JsonResponse({'error': 'Post only'}, status=405)

# --- 8. BULK IMPORT FEATURES (UPDATED) ---

@login_required
def download_employee_template(request):
    """
    Downloads a CSV template for bulk employee upload with specific fields.
    """
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="employee_template.csv"'

    writer = csv.writer(response)
    # 1. Define the headers exactly as requested
    writer.writerow(['Name', 'Last name', 'Department', 'Email', 'Phone no', 'Default password'])
    
    # 2. Add a sample row so the user knows how to fill it
    writer.writerow(['John', 'Doe', 'IT', 'john.doe@company.com', '9876543210', 'Welcome@123'])
    
    return response

@login_required
def upload_employee_bulk(request):
    """
    Processes the uploaded CSV/Excel file to create employees.
    """
    if request.method == "POST" and request.FILES.get('employee_file'):
        current_user = request.user
        
        # Verify Admin
        membership = OrganizationMember.objects.filter(user=current_user, role='ADMIN').first()
        if not membership:
            messages.error(request, "Unauthorized.")
            return redirect('company_dashboard')
        
        org = membership.organization
        csv_file = request.FILES['employee_file']
        
        # Simple file validation
        if not csv_file.name.endswith('.csv'):
            messages.error(request, "Please upload a CSV file.")
            return redirect('company_dashboard')
            
        try:
            # Decode file using utf-8-sig to handle Excel BOM automatically
            file_data = csv_file.read().decode("utf-8-sig")
            csv_data = io.StringIO(file_data)
            reader = csv.DictReader(csv_data)
            
            # Normalize headers (strip whitespace from CSV headers just in case)
            if reader.fieldnames:
                reader.fieldnames = [name.strip() for name in reader.fieldnames]

            added_count = 0
            
            for row in reader:
                # 1. Check Limits (Re-check every iteration)
                current_count = OrganizationMember.objects.filter(organization=org).count()
                if current_count >= org.max_users:
                    messages.warning(request, f"Limit reached. Stopped after adding {added_count} users.")
                    break
                
                # 2. Extract Data based on your specific headers
                first_name = row.get('Name', '').strip()
                last_name = row.get('Last name', '').strip()
                department = row.get('Department', '').strip()
                email = row.get('Email', '').strip()
                phone = row.get('Phone no', '').strip()
                password = row.get('Default password', '').strip()
                
                if not email or not password:
                    continue # Skip invalid rows

                # 3. Create User (Skip if exists)
                if User.objects.filter(email=email).exists():
                    continue

                try:
                    # Create the base user
                    user = User.objects.create_user(username=email, email=email, password=password)
                    user.first_name = first_name
                    user.last_name = last_name
                    user.account_type = 'EMPLOYEE'

                    # 4. Handle Custom Fields (Department / Phone)
                    # We check if your User model has these fields to prevent errors
                    if hasattr(user, 'department'):
                        user.department = department
                    if hasattr(user, 'phone'): 
                        user.phone = phone
                    
                    user.save()
                    
                    # Create Organization Member Link
                    OrganizationMember.objects.create(organization=org, user=user, role='MEMBER')
                    added_count += 1
                except Exception as e:
                    # Log error internally if needed, skipping row
                    continue 
            
            if added_count > 0:
                messages.success(request, f"Successfully imported {added_count} employees.")
            else:
                messages.warning(request, "No new employees were added (check emails or duplicates).")
                
        except Exception as e:
            messages.error(request, f"Error processing file: {str(e)}")
            
    return redirect('company_dashboard')


# --- 9. SUPERUSER DASHBOARD ---
@login_required
@user_passes_test(lambda u: u.is_superuser)
def superuser_dashboard(request):
    """
    Dashboard providing a global overview for the platform owner.
    """
    total_organizations = Organization.objects.count()
    total_users = User.objects.count()
    active_subscriptions = Subscription.objects.filter(status='ACTIVE').count()
    
    # Get all organizations to list them
    organizations = Organization.objects.all().order_by('-id')
    
    # Recent payments (Assuming you have a Payment model)
    recent_payments = Payment.objects.all().order_by('-id')[:10]

    context = {
        'total_organizations': total_organizations,
        'total_users': total_users,
        'active_subscriptions': active_subscriptions,
        'organizations': organizations,
        'recent_payments': recent_payments,
    }
    return render(request, 'superuser_dashboard.html', context)