import json
from datetime import timedelta

from django.contrib import messages
from django.db.models import Q, Sum
from django.shortcuts import redirect, render
from django.utils import timezone

from home.models import (
    AssessmentProgress,
    DailyActivity,
    ModuleProgress,
    Subscription,
    TrainingModule,
)


def posh_act_page_corp(request):
    """Same as posh_act_page but for company employees - no certificate option."""
    user = request.user

    has_access = Subscription.objects.filter(
        Q(user=user) | Q(organization__organizationmember__user=user),
        status="ACTIVE",
        plan__type__in=["POSH", "BOTH"],
    ).exists()

    if not has_access:
        messages.error(request, "Access Denied: Subscription Required.")
        return redirect("tutorial")

    # Build same context as posh_act_page
    modules = TrainingModule.objects.filter(module_type="POSH").order_by("order")
    progress_map = {}
    completed_count = 0

    for mod in modules:
        prog, _ = ModuleProgress.objects.get_or_create(user=user, module=mod)
        progress_map[mod.id] = prog.is_completed
        if prog.is_completed:
            completed_count += 1

    total_modules = modules.count()
    percent_complete = (
        int((completed_count / total_modules) * 100) if total_modules > 0 else 0
    )

    video_list = []
    ppt_list = []

    # Include all modules that are meant to be videos (not PPTs)
    video_modules = [m for m in modules if not m.ppt_file or m.video_file]
    previous_completed = True
    for mod in video_modules:
        is_completed = progress_map.get(mod.id, False)
        is_locked = not previous_completed
        item = {
            "id": mod.id,
            "title": mod.title,
            "is_completed": is_completed,
            "is_locked": is_locked,
            "thumb": mod.thumbnail.url if mod.thumbnail else "",
            "src": (
                mod.video_file.url
                if mod.video_file
                else "/media/training%20videos/Demo%20video.mp4"
            ),
            "url": "https://docs.google.com/presentation/d/1wb69ZQ4oYGYxOxzjNaTQP5bIfsB3tIKi/embed",
            "duration": mod.duration_seconds,
        }
        video_list.append(item)
        previous_completed = is_completed

    ppt_modules = [m for m in modules if m.ppt_file and not m.video_file]
    previous_completed = True
    for mod in ppt_modules:
        is_completed = progress_map.get(mod.id, False)
        is_locked = not previous_completed
        item = {
            "id": mod.id,
            "title": mod.title,
            "is_completed": is_completed,
            "is_locked": is_locked,
            "thumb": mod.thumbnail.url if mod.thumbnail else "",
            "src": "",
            "url": "https://docs.google.com/presentation/d/1wb69ZQ4oYGYxOxzjNaTQP5bIfsB3tIKi/embed",
        }
        ppt_list.append(item)
        if not is_completed:
            previous_completed = False

    today = timezone.now().date()
    total_mins_agg = (
        DailyActivity.objects.filter(user=user).aggregate(Sum("minutes_watched"))[
            "minutes_watched__sum"
        ]
        or 0
    )
    total_secs_agg = (
        DailyActivity.objects.filter(user=user).aggregate(Sum("seconds_watched"))[
            "seconds_watched__sum"
        ]
        or 0
    )
    total_seconds_watched = (total_mins_agg * 60) + total_secs_agg
    hours = total_seconds_watched // 3600
    minutes = (total_seconds_watched % 3600) // 60
    seconds = total_seconds_watched % 60
    formatted_total_time = f"{hours:02}:{minutes:02}:{seconds:02}"

    last_7_days = [(today - timedelta(days=i)) for i in range(6, -1, -1)]
    chart_labels = [d.strftime("%a") for d in last_7_days]
    chart_data = [
        (
            DailyActivity.objects.filter(user=user, date=d).first().minutes_watched
            if DailyActivity.objects.filter(user=user, date=d).exists()
            else 0
        )
        for d in last_7_days
    ]

    context = {
        "video_modules": video_list,
        "ppt_modules": ppt_list,
        "percent_complete": percent_complete,
        "completed_count": completed_count,
        "total_modules": total_modules,
        "chart_labels": json.dumps(chart_labels),
        "chart_data": json.dumps(chart_data),
        "total_seconds_watched": total_seconds_watched,
        "formatted_total_time": formatted_total_time,
        "is_final_quiz_passed": AssessmentProgress.objects.filter(
            user=user, assessment_type="POSH", is_passed=True
        ).exists(),
        "is_company_employee": True,
    }
    return render(request, "posh_act_page_corp.html", context)
