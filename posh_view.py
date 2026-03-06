def posh_act_page(request):
    user = request.user
    has_access = Subscription.objects.filter(
        Q(user=user) | Q(organization__organizationmember__user=user),
        status="ACTIVE",
        plan__type__in=["POSH", "BOTH"],
    ).exists()

    if not has_access:
        messages.error(request, "Access Denied: Subscription Required.")
        return redirect("tutorial")

    # 1. Fetch Modules
    modules = TrainingModule.objects.filter(module_type="POSH").order_by("order")

    # 2. Fetch User Progress
    progress_map = {}
    completed_count = 0

    # Initialize progress for all modules if not exists
    for mod in modules:
        prog, created = ModuleProgress.objects.get_or_create(user=user, module=mod)
        progress_map[mod.id] = prog.is_completed
        if prog.is_completed:
            completed_count += 1

    # 3. Calculate Overall Status
    total_modules = modules.count()
    percent_complete = (
        int((completed_count / total_modules) * 100) if total_modules > 0 else 0
    )

    # 4. Determine Locked Status & Split
    video_list = []
    ppt_list = []

    # Process Videos Sequence
    # Include all modules that are meant to be videos (not PPTs)
    # Changed from filtering by video_file to filtering by NOT having ppt_file
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
            # Use video file path with URL-encoded spaces
            "src": mod.video_file.url if mod.video_file else "/media/training%20videos/Demo%20video.mp4",
            "duration": mod.duration_seconds,
        }
        video_list.append(item)
        previous_completed = is_completed

    # Process PPT Sequence
    ppt_modules = [m for m in modules if m.ppt_file and not m.video_file]
    
    # UPDATED: Only include if it has PPT AND NO Video (to prevent duplicates)
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
            # UPDATED: Use new hardcoded path for PPT
            "url": "https://docs.google.com/presentation/d/1wb69ZQ4oYGYxOxzjNaTQP5bIfsB3tIKi/embed",
            "duration": mod.duration_seconds,
        }
        ppt_list.append(item)
        previous_completed = is_completed

    # 5. Daily Activity Stats for Chart (Last 7 days)
    today = timezone.now().date()

    # Calculate Total Study Time (Lifetime)
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

    last_7_days = [(today - timedelta(days=i)) for i in range(6, -1, -1)]
    chart_labels = [d.strftime("%a") for d in last_7_days]
    chart_data = []

    for d in last_7_days:
        activity = DailyActivity.objects.filter(user=user, date=d).first()
        chart_data.append(activity.minutes_watched if activity else 0)

    context = {
        "video_modules": video_list,
        "ppt_modules": ppt_list,
        "percent_complete": percent_complete,
        "completed_count": completed_count,
        "total_modules": total_modules,
        "chart_labels": json.dumps(chart_labels),
        "chart_data": json.dumps(chart_data),
        "chart_data": json.dumps(chart_data),
        # Remove duplicate key if present
        "total_seconds_watched": total_seconds_watched,
        "formatted_total_time": f"{total_seconds_watched // 3600:02}:{(total_seconds_watched % 3600) // 60:02}:{total_seconds_watched % 60:02}",
        "is_final_quiz_passed": AssessmentProgress.objects.filter(user=user, assessment_type="POSH", is_passed=True).exists(),
    }

    return render(request, "posh_act_page.html", context)


@csrf_exempt
@login_required
