from flask import Flask, render_template, request, session
import os
import csv
from itertools import permutations

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your_secret_key')

def load_activities():
    activities = []
    try:
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
    except Exception as e:
        print(f"Error loading activities: {e}")
        return []
    return activities

def calculate_sequence_cost(sequence, activities, current_day):
    """
    Calculate total delay cost for a given sequence of activities
    """
    try:
        total_delay_cost = 0
        sequence_scores = []
        
        # Create a dictionary for easy activity lookup
        activity_dict = {a['id']: a for a in activities}
        
        # Calculate max delay cost for normalization
        max_delay_cost = max(a['total_delay_cost_per_day'] for a in activities)
        
        for i, activity_id in enumerate(sequence):
            activity = activity_dict[activity_id]
            
            # Calculate delay cost for this activity
            if i > 0:  # Skip delay calculation for first activity
                delay_days = current_day - activity['start_day']
                if delay_days > 0:
                    delay_cost = delay_days * activity['total_delay_cost_per_day']
                    total_delay_cost += delay_cost
            else:
                delay_cost = 0
            
            # Calculate score for this activity
            is_first = i == 0
            score_details = calculate_score(
                activity.get('material', 1.0),  # material
                activity.get('equipment', True),  # equipment
                min(1.0, activity.get('available_manpower', activity['planned_manpower']) / activity['planned_manpower']) if activity['planned_manpower'] > 0 else 0,  # manpower_ratio
                activity['total_delay_cost_per_day'] if not is_first else 0,
                max_delay_cost,
                is_first
            )
            
            sequence_scores.append({
                'activity': activity,
                'score': score_details,
                'delay_cost': delay_cost
            })
        
        return total_delay_cost, sequence_scores
    except Exception as e:
        print(f"Error calculating sequence cost: {e}")
        return 0, []

def get_all_sequences(activities):
    """
    Generate all possible sequences of activities
    """
    try:
        return list(permutations([a['id'] for a in activities]))
    except Exception as e:
        print(f"Error generating sequences: {e}")
        return []

def find_best_sequence(activities, current_day):
    """
    Find the sequence with minimum total delay cost and return all sequence options
    """
    try:
        if not activities:
            return [], 0, []
            
        all_sequences = get_all_sequences(activities)
        sequence_options = []
        best_sequence = None
        min_cost = float('inf')
        
        for sequence in all_sequences:
            cost, scores = calculate_sequence_cost(sequence, activities, current_day)
            sequence_options.append({
                'sequence': sequence,
                'total_delay_cost': cost,
                'activities': scores,
                'is_best': False
            })
            
            if cost < min_cost:
                min_cost = cost
                best_sequence = sequence
        
        # Mark the best sequence
        for option in sequence_options:
            if option['sequence'] == best_sequence:
                option['is_best'] = True
                break
        
        return best_sequence, min_cost, sequence_options
    except Exception as e:
        print(f"Error finding best sequence: {e}")
        return [], 0, []

def get_parallel_activities(activities, current_day):
    """
    Get groups of parallel activities
    """
    try:
        dependency_groups = {}
        for activity in activities:
            if not activity['dependency_ids']:
                continue
            dep_key = ','.join(sorted(activity['dependency_ids']))
            if dep_key not in dependency_groups:
                dependency_groups[dep_key] = []
            dependency_groups[dep_key].append(activity)

        parallel_groups = []
        for group in dependency_groups.values():
            ready_activities = [a for a in group if a['start_day'] <= current_day]
            if len(ready_activities) > 1:
                parallel_groups.append(ready_activities)

        return parallel_groups
    except Exception as e:
        print(f"Error getting parallel activities: {e}")
        return []

def calculate_score(material, equipment, manpower_ratio, delay_cost_per_day, max_delay_cost_per_day, is_first_in_parallel=False):
    """
    Calculate score with detailed breakdown and improved delay score calculation
    """
    try:
        # Material score (30% weight)
        material_score = float(material) * 0.30
        
        # Equipment score (20% weight)
        equipment_score = 0.20 if equipment else 0
        
        # Manpower score (25% weight)
        manpower_score = float(manpower_ratio) * 0.25
        
        # Delay score (25% weight) - Improved calculation
        if is_first_in_parallel:
            delay_score = 0.25  # Full score for first activity
        else:
            # Calculate relative delay score based on cost ratio
            cost_ratio = float(delay_cost_per_day) / float(max_delay_cost_per_day) if max_delay_cost_per_day > 0 else 0
            # Use a softer reduction formula that maintains higher scores
            delay_score = 0.25 * (1 - (cost_ratio * 0.5))  # Only reduce by half the cost ratio
        
        # Calculate total score
        total_score = (material_score + equipment_score + manpower_score + delay_score) * 100
        
        # Return detailed breakdown
        return {
            'total_score': round(total_score, 2),
            'material_score': round(material_score * 100, 2),
            'equipment_score': round(equipment_score * 100, 2),
            'manpower_score': round(manpower_score * 100, 2),
            'delay_score': round(delay_score * 100, 2),
            'weights': {
                'material': 30,
                'equipment': 20,
                'manpower': 25,
                'delay': 25
            }
        }
    except Exception as e:
        print(f"Error calculating score: {e}")
        return {
            'total_score': 0,
            'material_score': 0,
            'equipment_score': 0,
            'manpower_score': 0,
            'delay_score': 0,
            'weights': {
                'material': 30,
                'equipment': 20,
                'manpower': 25,
                'delay': 25
            }
        }

def get_total_duration(activities):
    try:
        return sum(a['duration'] for a in activities)
    except Exception as e:
        print(f"Error calculating total duration: {e}")
        return 0

def get_planned_finish_day(activity, activities, actual_completion_days=None):
    try:
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
                    dep_activity = next((a for a in activities if a['id'] == dep), None)
                    if dep_activity:
                        dep_days.append(dep_activity['start_day'] + dep_activity['duration'] - 1)
            earliest_start = max(max(dep_days) + 1, activity['start_day']) if dep_days else activity['start_day']

        planned_finish = earliest_start + activity['duration'] - 1
        return planned_finish
    except Exception as e:
        print(f"Error calculating planned finish day: {e}")
        return activity['start_day'] + activity['duration'] - 1

def get_ready_activities(activities, actual_completion_days, current_day):
    try:
        ready = []
        for activity in activities:
            if activity['id'] in actual_completion_days and actual_completion_days[activity['id']] <= current_day:
                continue

            if not activity['dependency_ids']:
                if current_day >= activity['start_day']:
                    # Add available_manpower to activity
                    activity['available_manpower'] = activity['planned_manpower']
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
                # Add available_manpower to activity
                activity['available_manpower'] = activity['planned_manpower']
                ready.append(activity)

        return ready
    except Exception as e:
        print(f"Error getting ready activities: {e}")
        return []

def get_status(activity_id, actual_completion_days, current_day):
    try:
        if activity_id in actual_completion_days:
            if current_day > actual_completion_days[activity_id]:
                return "Completed"
            elif current_day == actual_completion_days[activity_id]:
                return "Completed Today"
        return "Pending"
    except Exception as e:
        print(f"Error getting status: {e}")
        return "Pending"

def build_cpm_mermaid(activities):
    try:
        nodes = []
        edges = []
        for act in activities:
            label = f"{act['id']}\\n{act['name']}\\nDuration: {act['duration']}d\\nCost: ₹{act['duration'] * (act['material_cost_per_day'] + act['manpower_cost_per_day'] + act['equipment_cost_per_day'])}"
            nodes.append(f'{act["id"]}["{label}"]')
            for dep in act['dependency_ids']:
                edges.append(f'{dep} --> {act["id"]}')
        
        return "flowchart LR\n" + "\n".join(nodes + edges)
    except Exception as e:
        print(f"Error building CPM mermaid: {e}")
        return "flowchart LR"

def build_daywise_costs(activities, summary, total_duration):
    try:
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
    except Exception as e:
        print(f"Error building daywise costs: {e}")
        return []

def get_activity_constraints(activity, current_day):
    try:
        constraints = []
        
        # Check manpower constraint
        if activity['planned_manpower'] > 1000:  # Assuming 1000 is max available manpower
            constraints.append({
                'message': f"⚠️ Manpower shortage: {activity['planned_manpower'] - 1000} workers needed",
                'is_critical': True,
                'recommendation': "Consider hiring additional workers or rescheduling the activity"
            })
        
        # Check start day constraint
        if current_day < activity['start_day']:
            constraints.append({
                'message': f"⚠️ Activity cannot start before day {activity['start_day']}",
                'is_critical': True,
                'recommendation': f"Wait until day {activity['start_day']} to start this activity"
            })
        
        # Check cost constraints
        total_cost = activity['duration'] * (
            activity['material_cost_per_day'] +
            activity['manpower_cost_per_day'] +
            activity['equipment_cost_per_day']
        )
        if total_cost > 1000000:  # Assuming 1M is budget threshold
            constraints.append({
                'message': f"⚠️ High cost activity: ₹{total_cost:,}",
                'is_critical': False,
                'recommendation': "Consider breaking down into smaller activities or optimizing resources"
            })
        
        return constraints
    except Exception as e:
        print(f"Error getting activity constraints: {e}")
        return []

@app.route('/', methods=['GET', 'POST'])
def index():
    try:
        activities = load_activities()
        if not activities:
            return "Error: Could not load activities", 500
            
        total_duration = get_total_duration(activities)
        if 'actual_completion_days' not in session:
            session['actual_completion_days'] = {}
        actual_completion_days = session['actual_completion_days']
        current_day = 1

        if request.method == 'POST':
            try:
                current_day = int(request.form.get('current_day', 1))
            except ValueError:
                current_day = 1

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
            
            # Find best sequence for parallel activities
            best_sequence, min_cost, sequence_options = find_best_sequence(ready_activities, current_day)
            
            # Get parallel groups
            parallel_groups = get_parallel_activities(ready_activities, current_day)
            
            # Update activity scores based on best sequence
            for activity in ready_activities:
                is_first_in_parallel = activity['id'] == best_sequence[0] if best_sequence else False
                activity['is_first_in_parallel'] = is_first_in_parallel
                
                # Get updated constraints from form with error handling
                try:
                    activity['available_manpower'] = int(request.form.get(f"manpower_{activity['id']}", activity['planned_manpower']))
                except (ValueError, TypeError):
                    activity['available_manpower'] = activity['planned_manpower']
                    
                try:
                    activity['material'] = float(request.form.get(f"material_{activity['id']}", 1.0))
                except (ValueError, TypeError):
                    activity['material'] = 1.0
                    
                activity['equipment'] = request.form.get(f"equipment_{activity['id']}", 'true').lower() == 'true'
                
                # Calculate manpower ratio
                manpower_ratio = min(1.0, activity['available_manpower'] / activity['planned_manpower']) if activity['planned_manpower'] > 0 else 0
                
                # Calculate delay cost for this activity
                if not is_first_in_parallel:
                    delay_days = current_day - activity['start_day']
                    if delay_days > 0:
                        activity['delay_cost_per_day'] = activity['total_delay_cost_per_day']
                    else:
                        activity['delay_cost_per_day'] = 0
                else:
                    activity['delay_cost_per_day'] = 0
                
                # Calculate score with detailed breakdown
                score_details = calculate_score(
                    activity['material'],  # material
                    activity['equipment'],  # equipment
                    manpower_ratio,  # manpower_ratio
                    activity['delay_cost_per_day'],
                    max((a.get('delay_cost_per_day', 0) for a in ready_activities), default=1),
                    is_first_in_parallel
                )
                
                # Add score details to activity
                activity.update(score_details)
                
                # Add parallel group information
                activity['parallel_group'] = None
                for group in parallel_groups:
                    if activity in group:
                        activity['parallel_group'] = [a['id'] for a in group]
                        break
                
                # Add sequence options with activity details
                activity['sequence_options'] = []
                for option in sequence_options:
                    sequence_details = {
                        'sequence': option['sequence'],
                        'total_delay_cost': option['total_delay_cost'],
                        'is_best': option['is_best'],
                        'activities': []
                    }
                    for act_score in option['activities']:
                        act = act_score['activity']
                        sequence_details['activities'].append({
                            'id': act['id'],
                            'name': act['name'],
                            'score': act_score['score'],
                            'delay_cost': act_score['delay_cost']
                        })
                    activity['sequence_options'].append(sequence_details)
                
                # Add constraints
                activity['constraints'] = get_activity_constraints(activity, current_day)
                
                per_day_cost = (
                    activity['material_cost_per_day'] +
                    activity['manpower_cost_per_day'] +
                    activity['equipment_cost_per_day']
                )
                activity['planned_cost'] = activity['duration'] * per_day_cost
                activity['delay_cost'] = 0

            # Sort activities by score
            ready_activities.sort(key=lambda x: x['total_score'], reverse=True)
            prev_ready_ids = ','.join([a['id'] for a in ready_activities])
            session['actual_completion_days'] = actual_completion_days

            sidebar_options = ["Project Overview", "CPM Schedule", "Cost Analysis", "Settings"]

            cpm_mermaid = build_cpm_mermaid(activities)
            daywise_costs = build_daywise_costs(activities, summary, total_duration)

            return render_template('index.html', activities=ready_activities, updated=True, current_day=current_day,
                                   actual_completion_days=actual_completion_days, all_activities=activities,
                                   total_duration=total_duration, prev_ready=prev_ready_ids, summary=summary,
                                   sidebar_options=sidebar_options, cpm_mermaid=cpm_mermaid, daywise_costs=daywise_costs,
                                   parallel_groups=parallel_groups, owner_name="Patchikolla Preetham Sai")

        else:
            session['actual_completion_days'] = {}
            actual_completion_days = {}
            current_day = 1
            ready_activities = get_ready_activities(activities, actual_completion_days, current_day)
            
            # Find best sequence for parallel activities
            best_sequence, min_cost, sequence_options = find_best_sequence(ready_activities, current_day)
            
            # Get parallel groups
            parallel_groups = get_parallel_activities(ready_activities, current_day)
            
            for activity in ready_activities:
                is_first_in_parallel = activity['id'] == best_sequence[0] if best_sequence else False
                activity['is_first_in_parallel'] = is_first_in_parallel
                
                # Set default values
                activity['available_manpower'] = activity['planned_manpower']
                activity['material'] = 1.0
                activity['equipment'] = True
                
                # Calculate manpower ratio
                manpower_ratio = 1.0  # Default to 100% for initial load
                
                # Calculate delay cost for this activity
                if not is_first_in_parallel:
                    delay_days = current_day - activity['start_day']
                    if delay_days > 0:
                        activity['delay_cost_per_day'] = activity['total_delay_cost_per_day']
                    else:
                        activity['delay_cost_per_day'] = 0
                else:
                    activity['delay_cost_per_day'] = 0
                
                # Calculate score with detailed breakdown
                score_details = calculate_score(
                    activity['material'],  # material
                    activity['equipment'],  # equipment
                    manpower_ratio,  # manpower_ratio
                    activity['delay_cost_per_day'],
                    max((a.get('delay_cost_per_day', 0) for a in ready_activities), default=1),
                    is_first_in_parallel
                )
                
                # Add score details to activity
                activity.update(score_details)
                
                # Add parallel group information
                activity['parallel_group'] = None
                for group in parallel_groups:
                    if activity in group:
                        activity['parallel_group'] = [a['id'] for a in group]
                        break
                
                # Add sequence options with activity details
                activity['sequence_options'] = []
                for option in sequence_options:
                    sequence_details = {
                        'sequence': option['sequence'],
                        'total_delay_cost': option['total_delay_cost'],
                        'is_best': option['is_best'],
                        'activities': []
                    }
                    for act_score in option['activities']:
                        act = act_score['activity']
                        sequence_details['activities'].append({
                            'id': act['id'],
                            'name': act['name'],
                            'score': act_score['score'],
                            'delay_cost': act_score['delay_cost']
                        })
                    activity['sequence_options'].append(sequence_details)
                
                # Add constraints
                activity['constraints'] = get_activity_constraints(activity, current_day)
                
                per_day_cost = (
                    activity['material_cost_per_day'] +
                    activity['manpower_cost_per_day'] +
                    activity['equipment_cost_per_day']
                )
                activity['planned_cost'] = activity['duration'] * per_day_cost
                activity['delay_cost'] = 0

            ready_activities.sort(key=lambda x: x['total_score'], reverse=True)
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
                                   sidebar_options=sidebar_options, cpm_mermaid=cpm_mermaid, daywise_costs=daywise_costs,
                                   parallel_groups=parallel_groups, owner_name="Patchikolla Preetham Sai")
    except Exception as e:
        print(f"Error in index route: {e}")
        return "An error occurred. Please try again.", 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)