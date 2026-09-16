from django.shortcuts import render, get_object_or_404
from django.http import HttpResponseRedirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required

from server.forms import LoginForm, AccountRegisterForm, AppointmentForm
from server.models import Account, Action, Appointment, ScheduleSlot
from server import views
from server import logger


def setup_view(request):
    if Account.objects.all().count() > 0:
        request.session['alert_success'] = "Setup has already been completed."
        return HttpResponseRedirect('/')
    # Get template data from the session
    template_data = views.parse_session(request, {'form_button': "Register"})
    # Proceed with rest of the view
    if request.method == 'POST':
        form = AccountRegisterForm(request.POST)
        if form.is_valid():
            views.register_user(
                form.cleaned_data['email'],
                form.cleaned_data['password_first'],
                form.cleaned_data['firstname'],
                form.cleaned_data['lastname'],
                Account.ACCOUNT_ADMIN
            )
            user = authenticate(
                username=form.cleaned_data['email'].lower(),  # Make sure it's lowercase
                password=form.cleaned_data['password_first']
            )
            logger.log(Action.ACTION_ACCOUNT, "Account login", user.account)
            login(request, user)
            request.session['alert_success'] = "Successfully setup Virtual Clinic's primary admin account."
            return HttpResponseRedirect('/profile/')
    else:
        form = AccountRegisterForm()
    template_data['form'] = form
    return render(request, 'virtualclinic/setup.html', template_data)


def logout_view(request):
    if request.user.is_authenticated:
        # Only log the action if the user has an associated Account record
        if hasattr(request.user, 'account'):
            logger.log(Action.ACTION_ACCOUNT, "Account logout", request.user.account)

    # Django deletes the session on logout, so we need to preserve any alerts currently waiting to be displayed
    saved_data = {}
    if request.session.has_key('alert_success'):
        saved_data['alert_success'] = request.session['alert_success']
    else:
        saved_data['alert_success'] = "You have successfully logged out."

    if request.session.has_key('alert_danger'):
        saved_data['alert_danger'] = request.session['alert_danger']

    logout(request)

    if 'alert_success' in saved_data:
        request.session['alert_success'] = saved_data['alert_success']
    if 'alert_danger' in saved_data:
        request.session['alert_danger'] = saved_data['alert_danger']

    return HttpResponseRedirect('/')


def login_view(request):
    # Authentication check. Users currently logged in cannot view this page.
    if request.user.is_authenticated:
        return HttpResponseRedirect('/profile/')
    elif Account.objects.all().count() == 0:
        return HttpResponseRedirect('/setup/')
    
    # get template data from session
    template_data = views.parse_session(request, {'form_button': "Login"})
    
    # Proceed with the rest of view
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            user = authenticate(
                username=form.cleaned_data['email'].lower(),
                password=form.cleaned_data['password']
            )
            
            # Check if authentication was successful BEFORE querying Account model
            if user is not None:
                try:
                    userInfo = Account.objects.get(user=user)
                    if userInfo.archive == False:
                        login(request, user)
                        logger.log(Action.ACTION_ACCOUNT, "Account login", request.user.account)
                        request.session['alert_success'] = "Successfully logged into VirtualClinic."
                        return HttpResponseRedirect('/profile/')
                    else:
                        request.session['alert_danger'] = "Account is archived! Please create a new account"
                        return HttpResponseRedirect('/register/')
                except Account.DoesNotExist:
                    request.session['alert_danger'] = "Account record not found."
            else:
                # Triggers when username/password doesn't match or account doesn't exist
                request.session['alert_danger'] = "Invalid email or password."
    else:
        form = LoginForm()
        
    template_data['form'] = form
    return render(request, 'virtualclinic/login.html', template_data)


def register_view(request):
    # Authentication check. Users logged in cannot view this page.
    if request.user.is_authenticated:
        return HttpResponseRedirect('/profile/')
    elif Account.objects.all().count() == 0:
        return HttpResponseRedirect('/setup/')
    # Get template data from session
    template_data = views.parse_session(request, {'form_button': "Register"})
    # Proceed with rest of the view
    if request.method == 'POST':
        form = AccountRegisterForm(request.POST)
        if form.is_valid():
            views.register_user(
                form.cleaned_data['email'],
                form.cleaned_data['password_first'],
                form.cleaned_data['firstname'],
                form.cleaned_data['lastname'],
                Account.ACCOUNT_PATIENT
            )
            user = authenticate(
                username=form.cleaned_data['email'].lower(),
                password=form.cleaned_data['password_first']
            )
            logger.log(Action.ACTION_ACCOUNT, "Account Login", user.account)
            login(request, user)
            request.session['alert_success'] = "Successfully registered with VirtualClinic."
            return HttpResponseRedirect('/profile/')
    else:
        form = AccountRegisterForm()
    template_data['form'] = form
    return render(request, 'virtualclinic/register.html', template_data)


def error_denied_view(request):
    # Authentication check
    authentication_result = views.authentication_check(request)
    if authentication_result is not None:
        return authentication_result
    # Get template data from session
    template_data = views.parse_session(request)
    # Proceed with rest of the view
    return render(request, 'virtualclinic/error/denied.html', template_data)


@login_required
def appointment_create_view(request):
    # Get template data from session
    template_data = views.parse_session(request, {'form_button': "Create Appointment"})
    
    if request.method == 'POST':
        form = AppointmentForm(request.POST)
        if form.is_valid():
            slot_id = form.cleaned_data['slot']
            selected_slot = get_object_or_404(ScheduleSlot, id=slot_id, is_booked=False)



            # Pass the logged-in user's account to generate()
            appointment = form.generate(selected_slot, patient_account=request.user.account)
            appointment.save()

            # Reserve the slot so it can't be booked again
            selected_slot.is_booked = True
            selected_slot.save()

            request.session['alert_success'] = "Appointment successfully booked!"
            return HttpResponseRedirect('/profile/')
    else:
        form = AppointmentForm()

    template_data['form'] = form
    template_data['available_slots'] = ScheduleSlot.objects.filter(is_booked=False).order_by('date', 'start_time')
    return render(request, 'virtualclinic/create_appointment.html', template_data)


@login_required
def profile_view(request):
    # Get template data from session
    template_data = views.parse_session(request)
    
    # Get current logged-in user's Account model
    user_account = request.user.account

    # Filter appointments based on user role
    if user_account.role == Account.ACCOUNT_DOCTOR:
        appointments = Appointment.objects.filter(doctor=user_account)
    elif user_account.role == Account.ACCOUNT_PATIENT:
        appointments = Appointment.objects.filter(patient=user_account)
    else:
        # Admins or other roles can view all appointments
        appointments = Appointment.objects.all()

    template_data['appointments'] = appointments
    return render(request, 'public/profile.html', template_data)

@login_required
def calendar_events_view(request):
    user_account = request.user.account

    # Ensure query targets only the active account's appointments
    if user_account.role == Account.ACCOUNT_PATIENT:
        appointments = Appointment.objects.filter(patient=user_account)
    elif user_account.role == Account.ACCOUNT_DOCTOR:
        appointments = Appointment.objects.filter(doctor=user_account)
    else:
        appointments = Appointment.objects.all()

    # Format into JSON expected by FullCalendar
    events = []
    for appt in appointments:
        events.append({
            'title': f"{appt.symptom.name} - {appt.doctor}",
            'start': appt.startTime.isoformat(),
            'end': appt.endTime.isoformat(),
        })

    return JsonResponse(events, safe=False)