from django.shortcuts import render
from django.http import HttpResponseRedirect
from django.db.models import Q

from server.forms import AppointmentForm
from server.models import Account, Appointment, Action
from server import views
from server import appointment
from server import logger
from server import message

from django.shortcuts import render, get_object_or_404
from django.http import HttpResponseRedirect
from django.contrib.auth.decorators import login_required

from server.models import Account, Appointment, ScheduleSlot
from server.forms import WalkInAppointmentForm
from server import views


def list_view(request):
    # 1. Add Account.ACCOUNT_ADMIN to allowed roles
    authentication_result = views.authentication_check(
        request,
        [Account.ACCOUNT_PATIENT, Account.ACCOUNT_DOCTOR, Account.ACCOUNT_ADMIN]
    )
    if authentication_result is not None:
        return authentication_result

    # Get template data from session
    template_data = views.parse_session(request)

    # Proceed with rest of the view
    appointment.parse_appointment_cancel(request, template_data)     # parse appointment cancelling

    # 2. Filter query based on role
    if request.user.account.role == Account.ACCOUNT_DOCTOR:
        template_data['query'] = Appointment.objects.filter(doctor=request.user.account)
    elif request.user.account.role == Account.ACCOUNT_PATIENT:
        template_data['query'] = Appointment.objects.filter(patient=request.user.account)
    else:
        # Admins (role 30) reach this branch and view all system appointments
        template_data['query'] = Appointment.objects.all()

    return render(request, 'virtualclinic/appointment/list.html', template_data)

def calendar_view(request):
    # Authentication check
    authentication_result = views.authentication_check(
        request,
        [Account.ACCOUNT_PATIENT, Account.ACCOUNT_DOCTOR]
    )
    if authentication_result is not None:
        return authentication_result
    # Get template data from session
    template_data = views.parse_session(request)
    # Proceed with rest of the view
    appointment.parse_appointment_cancel(request, template_data)  # parse appointment cancelling
    template_data['events'] = appointment.parse_appointments(request)   # Build list of appointments
    return render(request, 'virtualclinic/appointment/calendar.html', template_data)


def update_view(request):
    # Authentication check
    authentication_result = views.authentication_check(request, None, ['pk'])
    if authentication_result is not None:
        return authentication_result
    # Validation check. Make sure appointment exists for given pk
    pk = request.GET['pk']
    try:
        appointment = Appointment.objects.get(pk=pk)
    except Exception:
        request.session['alert_danger'] = "The requested appointment does not exist."
        return HttpResponseRedirect('/error/denied/')
    # Get template data from session
    template_data = views.parse_session(
        request,
        {
            'form_button': "Update Appointment",
            'form_action': "?pk="+pk,
            'appointment': appointment
        }
    )
    # Proceed with rest of the view
    request.POST._mutable = True
    if request.user.account.role == Account.ACCOUNT_PATIENT:
        request.POST['patient'] = request.user.account.pk
    elif request.user.account.role == Account.ACCOUNT_DOCTOR:
        request.POST['doctor'] = request.user.account.pk
    if request.method == 'POST':
        form = AppointmentForm(request.POST)
        if form.is_valid():
            form.assign(appointment)
            if Appointment.objects.filter(
                    ~Q(pk=appointment.pk),
                    Q(status="Active"),
                    Q(doctor=appointment.doctor) | Q(patient=appointment.patient),
                    Q(startTime__range=(appointment.startTime, appointment.endTime)) | Q(endTime__range=(appointment.startTime,appointment.endTime))).count():
                form.mark_error('startTime', 'This time conflicts with another appointment.')
                form.mark_error('endTime', 'This time conflicts with another appointment.')
            else:
                appointment.save()
                logger.log(Action.ACTION_APPOINTMENT, 'Appointment Updated', request.user.account)
                template_data['alert_success'] = "The appointment has been updated!"
                template_data['form'] = form
                if request.user.account.role == Account.ACCOUNT_PATIENT:
                    message.send_appointment_update(request, appointment,appointment.doctor)
                elif request.user.account.role == Account.ACCOUNT_DOCTOR:
                    message.send_appointment_update(request, appointment,appointment.patient)
                else:
                    message.send_appointment_update(request, appointment, appointment.patient)
                    message.send_appointment_update(request, appointment, appointment.doctor)
    else:
        form = AppointmentForm(appointment.get_populated_fields())
    if request.user.account.role == Account.ACCOUNT_PATIENT:
        form.disable_field('patient')
    elif request.user.account.role == Account.ACCOUNT_DOCTOR:
        form.disable_field('doctor')
    template_data['form'] = form
    return render(request, 'virtualclinic/appointment/update.html', template_data)


def create_view(request):
    # Authentication check
    authentication_result = views.authentication_check(
        request,
        [Account.ACCOUNT_PATIENT, Account.ACCOUNT_DOCTOR]
    )
    if authentication_result is not None:
        return authentication_result
    # Get template data from session
    template_data = views.parse_session(request, {'form_button':"Create"})
    # Proceed with rest of the view
    default = {}
    if request.user.account.role == Account.ACCOUNT_PATIENT:
        default['patient'] = request.user.account.pk
        if 'doctor' not in request.POST and request.user.account.profile.primaryCareDoctor is not None:
            default['doctor'] = request.user.account.profile.primaryCareDoctor.pk
    elif request.user.account.role == Account.ACCOUNT_DOCTOR:
        default['doctor'] = request.user.account.pk
    if 'hospital' not in request.POST and request.user.account.profile.prefHospital is not None:
        default['hospital'] = request.user.account.profile.prefHospital.pk
    request.POST._mutable = True
    request.POST.update(default)
    form = AppointmentForm(request.POST)
    if request.method == 'POST':
        if form.is_valid():
            appointment = form.generate()
            if Appointment.objects.filter(
                    Q(status="Active"),
                    Q(doctor=appointment.doctor) | Q(patient=appointment.patient),
                    Q(startTime__range=(appointment.startTime, appointment.endTime)) | Q(endTime__range=(appointment.startTime,appointment.endTime))).count():
                form.mark_error('startTime', 'this time conflicts with another appointment')
                form.mark_error('endTime', 'this time conflicts with another appointment')
            else:
                appointment.save()
                logger.log(Action.ACTION_APPOINTMENT, 'Appointment created', request.user.account)
                form = AppointmentForm(default)     # clean form when page is re displayed
                form._errors = {}
                request.session['alert_success'] = "Successfully created your appointment!"
                if request.user.account.role == Account.ACCOUNT_DOCTOR:
                    message.send_appointment_create(request,appointment,appointment.patient)
                elif request.user.account.role == Account.ACCOUNT_PATIENT:
                    message.send_appointment_create(request, appointment, appointment.doctor)
                else:
                    message.send_appointment_create(request, appointment, appointment.patient)
                    message.send_appointment_create(request, appointment, appointment.doctor)
                return HttpResponseRedirect('/appointment/list/')
    else:
        form._errors = {}
    if request.user.account.role == Account.ACCOUNT_PATIENT:
        form.disable_field('patient')
    elif request.user.account.role == Account.ACCOUNT_DOCTOR:
        form.disable_field('doctor')
    template_data['form'] = form
    return render(request, 'virtualclinic/appointment/create.html',template_data)

@login_required
def appointment_walkin_view(request):
    # Enforce staff/admin access check
    if request.user.account.role not in [Account.ACCOUNT_ADMIN, Account.ACCOUNT_DOCTOR]:
        return HttpResponseRedirect('/error/denied/')

    template_data = views.parse_session(request, {'form_button': "Create Walk-in Appointment"})

    if request.method == 'POST':
        form = WalkInAppointmentForm(request.POST)
        if form.is_valid():
            # Get selected patient and slot from the form
            patient_account = form.cleaned_data['patient']
            slot_id = form.cleaned_data['slot']
            selected_slot = get_object_or_404(ScheduleSlot, id=slot_id, is_booked=False)

            # Generate appointment assigned to the SELECTED patient
            appointment = form.generate(selected_slot, patient_account=patient_account)
            appointment.save()

            # Reserve the slot
            selected_slot.is_booked = True
            selected_slot.save()

            request.session['alert_success'] = f"Appointment successfully scheduled for {patient_account}!"
            return HttpResponseRedirect('/appointment/list/')
    else:
        form = WalkInAppointmentForm()

    template_data['form'] = form
    template_data['available_slots'] = ScheduleSlot.objects.filter(is_booked=False).order_by('date', 'start_time')
    
    # Updated template path to use your existing HTML file:
    return render(request, 'virtualclinic/create_appointment.html', template_data)