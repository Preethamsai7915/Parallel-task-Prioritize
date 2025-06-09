import csv
from flask import Flask, render_template, request, session
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your_secret_key')

def load_activities():
    activities = []
    with open('activities.csv', newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            activities.append({
                "id": row["id"],
                "name": row["name"],
                "duration": int(row["duration"]),
                "planned_manpower": int(row["planned_manpower"]),
                "dependency_ids": [d.strip() for d in row["dependency_ids"].split(',') if d.strip()],
                "start_day": int(row["start_day"]),
                "material_cost_per_day": int(row["material_cost_per_day"]),
                "manpower_cost_per_day": int(row["manpower_cost_per_day"]),
                "equipment_cost_per_day": int(row["equipment_cost_per_day"]),
                "total_delay_cost_per_day": int(row["total_delay_cost_per_day"]) if "total_delay_cost_per_day" in row and row["total_delay_cost_per_day"] else (
                    int(row["material_cost_per_day"]) + int(row["manpower_cost_per_day"]) + int(row["equipment_cost_per_day"])
                )
            })
    return activities

def get_parallel_activities(activities, current_day):
    # Group activities by their dependencies
    dependency_groups = {}
    for activity in activities:
        if not activity['dependency_ids']:
            continue
        dep_key = ','.join(sorted(activity['dependency_ids']))
        if dep_key not in dependency_groups:
            dependency_groups[dep_key] = []
        dependency_groups[dep_key].append(activity)
    
    # Find parallel activities that are ready to start
    parallel_groups = []
    for group in dependency_groups.values():
        ready_activities = [a for a in group if a['start_day'] <= current_day]
        if len(ready_activities) > 1:
            parallel_groups.append(ready_activities)
    
    return parallel_groups

def calculate_score(material, equipment, manpower_ratio, cost_score, delay_cost_per_day, max_delay_cost_per_day, is_first_in_parallel=False):
    material_score = material
    equipment_score = 1 if equipment else 0
    manpower_score = min(manpower_ratio, 1.0)
    
    # Only consider delay score if not the first activity in parallel group
    if is_first_in_parallel:
        delay_score = 1.0
    else:
        delay_score = 1.0
        if max_delay_cost_per_day > 0:
            delay_score = 1 - (delay_cost_per_day / max_delay_cost_per_day)
            if delay_cost_per_day == max_delay_cost_per_day:
                delay_score = 1.0
            elif delay_score < 0:
                delay_score = 0.0
    
    score = (
        0.30 * material_score +
        0.20 * equipment_score +
        0.25 * manpower_score +
        0.25 * delay_score
    ) * 100
    return round(score, 2)

def get_total_duration(activities):
    return sum(a['duration'] for a in activities)

def get_planned_finish_day(activity, activities, actual_completion_days=None):
    if actual_completion_days is None:
        actual_completion_days = {}

    if not activity['dependency_ids']:
        earliest_start = activity['start_day']
    else:
        dep_days = []
        for dep in activity['dependency_ids']:
            if dep in actual_completion_days:
                dep_days.append(actual_completion_days[dep])
            else:
                dep_activity = next(a for a in activities if a['id'] == dep)
                dep_days.append(dep_activity['start_day'] + dep_activity['duration'] - 1)
        earliest_start = max(max(dep_days) + 1, activity['start_day'])

    planned_finish = earliest_start + activity['duration'] - 1
    return planned_finish

def get_ready_activities(activities, actual_completion_days, current_day):
    ready = []
    for activity in activities:
        if activity['id'] in actual_completion_days and actual_completion_days[activity['id']] <= current_day:
            continue

        if not activity['dependency_ids']:
            if current_day >= activity['start_day']:
                ready.append(activity)
            continue

        dep_completion_days = []
        all_deps_completed = True
        for dep in activity['dependency_ids']:
            if dep not in actual_completion_days:
                all_deps_completed = False
                break
            dep_completion_days.append(actual_completion_days[dep])

        if not all_deps_completed:
            continue

        latest_dep_completion = max(dep_completion_days)
        if current_day >= latest_dep_completion + 1 and current_day >= activity['start_day']:
            ready.append(activity)

    return ready

def get_status(activity_id, actual_completion_days, current_day):
    if activity_id in actual_completion_days:
        if current_day > actual_completion_days[activity_id]:
            return "Completed"
        elif current_day == actual_completion_days[activity_id]:
            return "Completed Today"
    return "Pending"

def build_cpm_mermaid(activities):
    nodes = []
    edges = []
    for act in activities:
        label = f"{act['id']}\\n{act['name']}\\nDuration: {act['duration']}d\\nCost: ₹{act['duration'] * (act['material_cost_per_day'] + act['manpower_cost_per_day'] + act['equipment_cost_per_day'])}"
        nodes.append(f'{act["id"]}["{label}"]')
        for dep in act['dependency_ids']:
            edges.append(f'{dep} --> {act["id"]}')
    
    return "flowchart LR\n" + "\n".join(nodes + edges)

def build_daywise_costs(activities, summary, total_duration):
    daywise = []
    for day in range(1, total_duration+1):
        planned = 0
        actual = 0
        overrun = 0
        details = []
        for act in summary:
            per_day_cost = act['planned_cost'] // act['duration']
            planned_start = get_planned_finish_day(act, activities, {}) - act['duration'] + 1
            planned_finish = get_planned_finish_day(act, activities, {})
            if planned_start <= day <= planned_finish:
                planned += per_day_cost
            if isinstance(act['actual_completion_day'], int):
                actual_start = act['actual_completion_day'] - act['duration'] + 1
                actual_finish = act['actual_completion_day']
                if actual_start <= day <= actual_finish:
                    actual += per_day_cost
            if isinstance(act['actual_completion_day'], int):
                planned_finish = get_planned_finish_day(act, activities, {})
                if day > planned_finish and actual_start <= day <= actual_finish:
                    overrun += per_day_cost
            details.append({
                "name": act['name'],
                "planned": per_day_cost if planned_start <= day <= planned_finish else 0,
                "actual": per_day_cost if isinstance(act['actual_completion_day'], int) and actual_start <= day <= actual_finish else 0,
                "overrun": per_day_cost if isinstance(act['actual_completion_day'], int) and day > planned_finish and actual_start <= day <= actual_finish else 0,
                "status": act['status']
            })
        daywise.append({
            "day": day,
            "planned": planned,
            "actual": actual,
            "overrun": overrun,
            "details": details
        })
    return daywise

@app.route('/', methods=['GET', 'POST'])
def index():
    activities = load_activities()
    total_duration = get_total_duration(activities)
    if 'actual_completion_days' not in session:
        session['actual_completion_days'] = {}
    actual_completion_days = session['actual_completion_days']
    current_day = 1

    if request.method == 'POST':
        current_day = int(request.form.get('current_day', 1))

        for activity in activities:
            checkbox = request.form.get(f"complete_{activity['id']}")
            if checkbox == 'on':
                if activity['id'] not in actual_completion_days or actual_completion_days[activity['id']] > current_day:
                    actual_completion_days[activity['id']] = current_day
            elif activity['id'] in actual_completion_days and actual_completion_days[activity['id']] >= current_day:
                del actual_completion_days[activity['id']]

        summary = []
        for activity in activities:
            status = get_status(activity['id'], actual_completion_days, current_day)
            actual_finish = actual_completion_days.get(activity['id'])
            planned_finish = get_planned_finish_day(activity, activities, actual_completion_days)
            per_day_cost = (
                activity['material_cost_per_day'] +
                activity['manpower_cost_per_day'] +
                activity['equipment_cost_per_day']
            )
            planned_cost = activity['duration'] * per_day_cost
            delay_days = 0
            actual_cost = planned_cost
            delay_cost = 0
            if actual_finish is not None:
                delay_days = max(0, actual_finish - planned_finish)
                actual_cost = (activity['duration'] + delay_days) * per_day_cost
                delay_cost = actual_cost - planned_cost
            summary.append({
                **activity,
                "status": status,
                "actual_completion_day": actual_finish if actual_finish is not None else "-",
                "planned_finish_day": planned_finish,
                "delay_days": delay_days,
                "planned_cost": planned_cost,
                "actual_cost": actual_cost,
                "delay_cost": delay_cost
            })

        ready_activities = get_ready_activities(activities, actual_completion_days, current_day)
        parallel_groups = get_parallel_activities(ready_activities, current_day)

        for activity in ready_activities:
            material_input = float(request.form.get(f"{activity['id']}_material", 1.0))
            equipment_input = request.form.get(f"{activity['id']}_equipment", 'yes') == 'yes'
            manpower_input = int(request.form.get(f"{activity['id']}_manpower", activity['planned_manpower']))

            activity['material'] = material_input
            activity['equipment'] = equipment_input
            activity['available_manpower'] = manpower_input
            manpower_ratio = manpower_input / activity['planned_manpower'] if activity['planned_manpower'] > 0 else 1.0

            planned_finish = get_planned_finish_day(activity, activities, actual_completion_days)
            delay_days = max(0, current_day - planned_finish)
            per_day_cost = (
                activity['material_cost_per_day'] +
                activity['manpower_cost_per_day'] +
                activity['equipment_cost_per_day']
            )
            delay_cost = delay_days * per_day_cost
            activity['delay_cost'] = delay_cost
            activity['planned_cost'] = activity['duration'] * per_day_cost
            activity['delay_cost_per_day'] = activity.get('total_delay_cost_per_day', per_day_cost)

        max_delay_cost_per_day = max((a.get('delay_cost_per_day', 0) for a in ready_activities), default=1)

        for activity in ready_activities:
            material_input = activity['material']
            equipment_input = activity['equipment']
            manpower_ratio = activity['available_manpower'] / activity['planned_manpower'] if activity['planned_manpower'] > 0 else 1.0
            delay_cost_per_day = activity.get('delay_cost_per_day', 0)
            
            # Check if this activity is first in any parallel group
            is_first_in_parallel = False
            for group in parallel_groups:
                if activity in group and activity == group[0]:
                    is_first_in_parallel = True
                    break
            
            activity['score'] = calculate_score(
                material_input, 
                equipment_input, 
                manpower_ratio, 
                1.0, 
                delay_cost_per_day, 
                max_delay_cost_per_day,
                is_first_in_parallel
            )

        ready_activities.sort(key=lambda x: x['score'], reverse=True)
        prev_ready_ids = ','.join([a['id'] for a in ready_activities])
        session['actual_completion_days'] = actual_completion_days

        sidebar_options = ["Project Overview", "CPM Schedule", "Cost Analysis", "Settings"]

        cpm_mermaid = build_cpm_mermaid(activities)
        daywise_costs = build_daywise_costs(activities, summary, total_duration)

        return render_template('index.html', activities=ready_activities, updated=True, current_day=current_day,
                               actual_completion_days=actual_completion_days, all_activities=activities,
                               total_duration=total_duration, prev_ready=prev_ready_ids, summary=summary,
                               sidebar_options=sidebar_options, cpm_mermaid=cpm_mermaid, daywise_costs=daywise_costs, owner_name="Patchikolla Preetham Sai")

    else:
        session['actual_completion_days'] = {}
        actual_completion_days = {}
        current_day = 1
        ready_activities = get_ready_activities(activities, actual_completion_days, current_day)
        parallel_groups = get_parallel_activities(ready_activities, current_day)
        
        for activity in ready_activities:
            activity['material'] = 1.0
            activity['equipment'] = True
            activity['available_manpower'] = activity['planned_manpower']
            activity['delay_cost_per_day'] = activity.get('total_delay_cost_per_day', activity['material_cost_per_day'] + activity['manpower_cost_per_day'] + activity['equipment_cost_per_day'])
            
            # Check if this activity is first in any parallel group
            is_first_in_parallel = False
            for group in parallel_groups:
                if activity in group and activity == group[0]:
                    is_first_in_parallel = True
                    break
            
            activity['score'] = calculate_score(
                1.0, 
                True, 
                1.0, 
                1.0, 
                activity['delay_cost_per_day'], 
                1,
                is_first_in_parallel
            )
            
            per_day_cost = (
                activity['material_cost_per_day'] +
                activity['manpower_cost_per_day'] +
                activity['equipment_cost_per_day']
            )
            activity['planned_cost'] = activity['duration'] * per_day_cost
            activity['delay_cost'] = 0

        ready_activities.sort(key=lambda x: x['score'], reverse=True)
        prev_ready_ids = ','.join([a['id'] for a in ready_activities])

        summary = []
        for activity in activities:
            status = get_status(activity['id'], actual_completion_days, current_day)
            actual_finish = actual_completion_days.get(activity['id'])
            planned_finish = get_planned_finish_day(activity, activities, actual_completion_days)
            per_day_cost = (
                activity['material_cost_per_day'] +
                activity['manpower_cost_per_day'] +
                activity['equipment_cost_per_day']
            )
            planned_cost = activity['duration'] * per_day_cost
            delay_days = 0
            actual_cost = planned_cost
            delay_cost = 0
            summary.append({
                **activity,
                "status": status,
                "actual_completion_day": actual_finish if actual_finish is not None else "-",
                "planned_finish_day": planned_finish,
                "delay_days": delay_days,
                "planned_cost": planned_cost,
                "actual_cost": actual_cost,
                "delay_cost": delay_cost
            })

        sidebar_options = ["Project Overview", "CPM Schedule", "Cost Analysis", "Settings"]

        cpm_mermaid = build_cpm_mermaid(activities)
        daywise_costs = build_daywise_costs(activities, summary, total_duration)

        return render_template('index.html', activities=ready_activities, updated=False, current_day=current_day,
                               actual_completion_days=actual_completion_days, all_activities=activities,
                               total_duration=total_duration, prev_ready=prev_ready_ids, summary=summary,
                               sidebar_options=sidebar_options, cpm_mermaid=cpm_mermaid, daywise_costs=daywise_costs, owner_name="Patchikolla Preetham Sai")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)