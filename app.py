from flask import Flask, render_template, request, session
import os
import csv
from itertools import permutations

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your_secret_key')

# Ensure the application is in production mode
app.config['ENV'] = 'production'
app.config['DEBUG'] = False

def load_activities():
    activities = []
    try:
        # Get the absolute path to the activities.csv file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        csv_path = os.path.join(current_dir, 'activities.csv')
        
        if not os.path.exists(csv_path):
            print(f"Error: activities.csv not found at {csv_path}")
            return []
            
        with open(csv_path, newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                try:
                    # Calculate base delay cost without site overheads
                    base_delay_cost = int(row["manpower_cost_per_day"]) + int(row["owned_equipment_om_cost_per_day"])
                    
                    # Get site overhead cost
                    site_overhead = int(row["site_overhead_cost_per_day"]) if "site_overhead_cost_per_day" in row else 0
                    
                    activities.append({
                        "id": row["id"],
                        "name": row["name"],
                        "duration": int(row["duration"]),
                        "planned_manpower": int(row["planned_manpower"]),
                        "dependency_ids": [d.strip() for d in row["dependency_ids"].split(',') if d.strip()],
                        "start_day": int(row["start_day"]),
                        "manpower_cost_per_day": int(row["manpower_cost_per_day"]),
                        "rented_equipment_cost_per_day": int(row["rented_equipment_cost_per_day"]),
                        "owned_equipment_om_cost_per_day": int(row["owned_equipment_om_cost_per_day"]),
                        "no_equipment_cost_per_day": int(row["no_equipment_cost_per_day"]),
                        "site_overhead_cost_per_day": site_overhead,
                        "base_delay_cost_per_day": base_delay_cost,  # Store base delay cost separately
                        "total_delay_cost_per_day": base_delay_cost  # Initialize without site overheads
                    })
                except (ValueError, KeyError) as e:
                    print(f"Error processing row: {row}, Error: {e}")
                    continue
                    
        return activities
    except Exception as e:
        print(f"Error loading activities: {e}")
        return []

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
            delay_cost=0
            
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
                is_first,
                activity,
                activities  # Pass the activities list as all_activities
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

def is_activity_critical(activity, critical_paths):
    """Check if an activity is on any critical path."""
    try:
        for path in critical_paths:
            if any(act['id'] == activity['id'] for act in path):
                return True
        return False
    except Exception as e:
        print(f"Error checking if activity is critical: {e}")
        return False

def is_activity_close_to_critical(activity, critical_paths, threshold=2):
    """Check if an activity is close to any critical path within a threshold."""
    try:
        for path in critical_paths:
            # Check if activity is directly connected to any critical path activity
            for critical_activity in path:
                # Check if activity is a dependency of critical activity
                if activity['id'] in critical_activity['dependency_ids']:
                    return True
                # Check if critical activity is a dependency of this activity
                if critical_activity['id'] in activity['dependency_ids']:
                    return True
                # Check if they share dependencies
                if set(activity['dependency_ids']) & set(critical_activity['dependency_ids']):
                    return True
        return False
    except Exception as e:
        print(f"Error checking if activity is close to critical: {e}")
        return False

def calculate_score(material, equipment, manpower_ratio, delay_cost_per_day, max_delay_cost_per_day, is_first_in_parallel=False, activity=None, all_activities=None):
    """
    Calculate score for an activity based on various factors
    """
    try:
        # Calculate base daily costs based on available manpower
        if activity:
            available_manpower = activity.get('available_manpower', activity['planned_manpower'])
            manpower_ratio = available_manpower / activity['planned_manpower']
            base_manpower_cost = activity['manpower_cost_per_day'] * manpower_ratio
            
            # Get equipment cost based on type
            equipment_cost = get_equipment_cost(activity, activity.get('equipment_type', 'owned'))
            
            # Base daily cost is the sum of manpower and equipment costs
            base_daily_cost = base_manpower_cost + equipment_cost
            
            # Update activity with calculated costs
            activity['base_delay_cost_per_day'] = base_daily_cost
        
        # Calculate delay score (35%)
        delay_score = 0
        if activity:
            # First check if activity has free float and is within it
            free_float = activity.get('free_float', 0)
            current_delay = activity.get('current_delay', 0)
            
            # If activity has free float and current delay is within it, no delay cost or score
            if free_float > 0 and current_delay <= free_float:
                activity['total_delay_cost_per_day'] = 0
                delay_score = 0
            else:
                # Only calculate delay score if beyond free float or no free float
                if activity.get('parallel_group'):
                    # For parallel activities, calculate proportional score based on max delay cost
                    parallel_activities = activity['parallel_group']
                    
                    # Filter out activities that are within their free float
                    effective_parallel_activities = []
                    for act in parallel_activities:
                        act_free_float = act.get('free_float', 0)
                        act_current_delay = act.get('current_delay', 0)
                        if act_free_float == 0 or act_current_delay > act_free_float:
                            effective_parallel_activities.append(act)
                    
                    if effective_parallel_activities:
                        max_parallel_delay_cost = max(act.get('total_delay_cost_per_day', 0) for act in effective_parallel_activities)
                        current_activity_delay_cost = activity.get('total_delay_cost_per_day', 0)
                        
                        if max_parallel_delay_cost > 0:
                            delay_score = round((current_activity_delay_cost * 35) / max_parallel_delay_cost, 2)
                else:
                    # For non-parallel activities
                    if all_activities:
                        # Find activities with the same dependencies
                        same_dep_activities = [a for a in all_activities if a.get('dependency_ids') == activity.get('dependency_ids')]
                        if len(same_dep_activities) > 1:
                            # Filter out activities that are within their free float
                            effective_same_dep_activities = []
                            for act in same_dep_activities:
                                act_free_float = act.get('free_float', 0)
                                act_current_delay = act.get('current_delay', 0)
                                if act_free_float == 0 or act_current_delay > act_free_float:
                                    effective_same_dep_activities.append(act)
                            
                            if effective_same_dep_activities:
                                max_delay_cost = max(act.get('total_delay_cost_per_day', 0) for act in effective_same_dep_activities)
                                current_delay_cost = activity.get('total_delay_cost_per_day', 0)
                                
                                if max_delay_cost > 0:
                                    delay_score = round((current_delay_cost * 35) / max_delay_cost, 2)
                        else:
                            # Single activity with no parallel activities
                            delay_score = 35
                    else:
                        # No other activities to compare with
                        delay_score = 35

        # Calculate equipment score (25%)
        equipment_score = 0
        if activity:
            if equipment == 'rented':
                equipment_score = 25  # Full score for rented equipment
            elif equipment == 'owned':
                # Calculate score based on relative cost
                rented_cost = activity.get('rented_equipment_cost_per_day', 0)
                owned_cost = activity.get('owned_equipment_om_cost_per_day', 0)
                if rented_cost > 0:
                    # Score is proportional to owned cost relative to rented cost
                    equipment_score = (owned_cost / rented_cost) * 25
                else:
                    equipment_score = 0
            elif equipment == 'no_equipment':
                equipment_score = 0  # Zero score for no equipment
            else:
                equipment_score = 0  # Default to zero score for any other case

        # Calculate manpower score (15%)
        manpower_score = manpower_ratio * 15

        # Calculate material score (10%)
        material_score = material * 10

        # Calculate critical path score (15%)
        critical_path_score = 0
        if activity:
            # Get critical paths from the activity's context
            critical_paths = activity.get('critical_paths', [])
            
            # Check if this activity is on any critical path
            if is_activity_critical(activity, critical_paths):
                critical_path_score = 15
            # Check if activity is close to critical path
            elif is_activity_close_to_critical(activity, critical_paths):
                critical_path_score = 10
            elif activity.get('parallel_group'):
                # Check if all activities in parallel group are critical
                all_critical = True
                for parallel_activity in activity['parallel_group']:
                    if not is_activity_critical(parallel_activity, critical_paths):
                        all_critical = False
                        break
                if all_critical:
                    critical_path_score = 15

        # Calculate total score
        total_score = delay_score + equipment_score + manpower_score + material_score + critical_path_score

        # Return detailed score breakdown
        return {
            'total_score': round(total_score, 2),
            'delay_score': round(delay_score, 2),
            'equipment_score': round(equipment_score, 2),
            'manpower_score': round(manpower_score, 2),
            'material_score': round(material_score, 2),
            'critical_path_score': round(critical_path_score, 2),
            'weights': {
                'delay': 35,
                'equipment': 25,
                'manpower': 15,
                'critical_path': 15,
                'material': 10
            }
        }
    except Exception as e:
        print(f"Error calculating score: {e}")
        # Return default scores in case of error
        return {
            'total_score': 50.0,
            'delay_score': 17.5,
            'equipment_score': 0,
            'manpower_score': 7.5,
            'material_score': 5.0,
            'critical_path_score': 7.5,
            'weights': {
                'delay': 35,
                'equipment': 25,
                'manpower': 15,
                'critical_path': 15,
                'material': 10
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
            label = f"{act['id']}\\n{act['name']}\\nDuration: {act['duration']}d\\nCost: ₹{act['duration'] * (act['manpower_cost_per_day'] + act['rented_equipment_cost_per_day'])}"
            nodes.append(f'{act["id"]}["{label}"]')
            for dep in act['dependency_ids']:
                edges.append(f'{dep} --> {act["id"]}')
        
        return "flowchart LR\n" + "\n".join(nodes + edges)
    except Exception as e:
        print(f"Error building CPM mermaid: {e}")
        return "flowchart LR"

def get_critical_path(activities):
    try:
        # Calculate earliest start and finish times
        earliest_start = {act['id']: 0 for act in activities}
        earliest_finish = {act['id']: 0 for act in activities}
        
        # Forward pass
        for act in activities:
            if not act['dependency_ids']:
                earliest_start[act['id']] = act['start_day']
            else:
                earliest_start[act['id']] = max(earliest_finish[dep] for dep in act['dependency_ids'])
            earliest_finish[act['id']] = earliest_start[act['id']] + act['duration']
        
        # Calculate latest start and finish times
        project_duration = max(earliest_finish.values())
        latest_finish = {act['id']: project_duration for act in activities}
        latest_start = {act['id']: 0 for act in activities}
        
        # Backward pass
        for act in reversed(activities):
            if not any(act['id'] in other['dependency_ids'] for other in activities):
                latest_finish[act['id']] = project_duration
            else:
                latest_finish[act['id']] = min(latest_start[dep] for dep in [a['id'] for a in activities if act['id'] in a['dependency_ids']])
            latest_start[act['id']] = latest_finish[act['id']] - act['duration']
        
        # Calculate float/slack for each activity
        float_times = {}
        for act in activities:
            float_times[act['id']] = latest_start[act['id']] - earliest_start[act['id']]
        
        # Find all critical paths
        critical_paths = []
        
        def find_paths(current_path, current_activity):
            if not current_activity:
                return
            
            current_path.append(current_activity)
            
            # If this is an end activity (no dependents)
            if not any(current_activity['id'] in act['dependency_ids'] for act in activities):
                if len(current_path) > 0:
                    critical_paths.append(current_path.copy())
                current_path.pop()
                return
            
            # Find all next activities with zero float
            next_activities = []
            for act in activities:
                if current_activity['id'] in act['dependency_ids'] and float_times[act['id']] == 0:
                    next_activities.append(act)
            
            # Recursively find all paths
            for next_act in next_activities:
                find_paths(current_path, next_act)
            
            current_path.pop()
        
        # Start from activities with no dependencies
        start_activities = [act for act in activities if not act['dependency_ids']]
        for start_act in start_activities:
            if float_times[start_act['id']] == 0:  # Only start from critical activities
                find_paths([], start_act)
        
        # Calculate duration for each path
        path_durations = []
        for path in critical_paths:
            duration = sum(act['duration'] for act in path)
            path_durations.append(duration)
        
        # Verify all paths have the same duration
        if path_durations and not all(d == path_durations[0] for d in path_durations):
            print("Warning: Critical paths have different durations")
        
        # Return all critical paths and the total duration (sum of critical path activities)
        total_duration = sum(act['duration'] for act in critical_paths[0]) if critical_paths else 0
        return critical_paths, total_duration
    except Exception as e:
        print(f"Error calculating critical path: {e}")
        return [], 0

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
            activity['manpower_cost_per_day'] +
            activity['rented_equipment_cost_per_day']
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

def get_equipment_cost(activity, equipment_type):
    """Helper function to get equipment cost based on type"""
    if equipment_type == 'rented':
        return activity['rented_equipment_cost_per_day']
    elif equipment_type == 'owned':
        return activity['owned_equipment_om_cost_per_day']
    else:  # no_equipment
        return activity['no_equipment_cost_per_day']

def update_activity_delay_costs(activities, critical_paths, current_day):
    try:
        for activity in activities:
            # Calculate base daily cost based on available manpower and equipment
            available_manpower = activity.get('available_manpower', activity['planned_manpower'])
            manpower_ratio = available_manpower / activity['planned_manpower']
            base_manpower_cost = activity['manpower_cost_per_day'] * manpower_ratio
            
            # Get equipment cost based on type
            equipment_type = activity.get('equipment_type', 'owned')
            equipment_cost = get_equipment_cost(activity, equipment_type)
            
            # Base daily cost is the sum of manpower and equipment costs
            base_daily_cost = base_manpower_cost + equipment_cost
            
            # Check if activity is critical or close to critical
            is_critical = is_activity_critical(activity, critical_paths)
            is_close_to_critical = is_activity_close_to_critical(activity, critical_paths)
            
            # Calculate total delay cost
            if is_critical:
                # For critical path activities, always include full site overhead
                total_delay_cost = base_daily_cost + activity['site_overhead_cost_per_day']
            elif is_close_to_critical and activity.get('is_delayed', False):
                # For activities close to critical path, include half site overhead only if delayed
                total_delay_cost = base_daily_cost + (activity['site_overhead_cost_per_day'] * 0.5)
            else:
                # For other activities, no site overhead
                total_delay_cost = base_daily_cost
            
            # Update activity with calculated costs
            activity['base_delay_cost_per_day'] = base_daily_cost
            activity['total_delay_cost_per_day'] = total_delay_cost
            activity['is_critical'] = is_critical
            activity['is_close_to_critical'] = is_close_to_critical
    except Exception as e:
        print(f"Error updating activity delay costs: {e}")

def get_float_values(activities):
    # Calculate early start and early finish
    for activity in activities:
        activity['early_start'] = 0
        activity['early_finish'] = 0
        activity['late_start'] = 0
        activity['late_finish'] = 0
        activity['total_float'] = 0
        activity['free_float'] = 0

    # Forward pass
    for activity in activities:
        if not activity.get('dependency_ids'):
            activity['early_start'] = 1
        else:
            max_early_finish = 0
            for dep_id in activity['dependency_ids']:
                dep = next((a for a in activities if a['id'] == dep_id), None)
                if dep and dep['early_finish'] > max_early_finish:
                    max_early_finish = dep['early_finish']
            activity['early_start'] = max_early_finish + 1
        activity['early_finish'] = activity['early_start'] + activity['duration'] - 1

    # Find project duration
    project_duration = max(activity['early_finish'] for activity in activities)

    # Backward pass
    for activity in reversed(activities):
        # Find successors
        successors = [a for a in activities if a.get('dependency_ids') and activity['id'] in a['dependency_ids']]
        
        if not successors:
            activity['late_finish'] = project_duration
        else:
            min_late_start = float('inf')
            for succ in successors:
                if succ['late_start'] < min_late_start:
                    min_late_start = succ['late_start']
            activity['late_finish'] = min_late_start - 1
        
        activity['late_start'] = activity['late_finish'] - activity['duration'] + 1
        
        # Calculate floats
        activity['total_float'] = activity['late_start'] - activity['early_start']
        activity['free_float'] = float('inf')
        
        if successors:
            min_early_start = min(succ['early_start'] for succ in successors)
            activity['free_float'] = min_early_start - activity['early_finish'] - 1
        else:
            activity['free_float'] = project_duration - activity['early_finish']
        
        # Ensure floats are non-negative
        activity['total_float'] = max(0, activity['total_float'])
        activity['free_float'] = max(0, activity['free_float'])

    return activities

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

        # Calculate critical path
        critical_paths, project_duration = get_critical_path(activities)
        
        if request.method == 'POST':
            try:
                current_day = int(request.form.get('current_day', 1))
            except ValueError:
                current_day = 1
            
            # Update activity completion status and costs
            for activity in activities:
                checkbox = request.form.get(f"complete_{activity['id']}")
                if checkbox == 'on':
                    if activity['id'] not in actual_completion_days or actual_completion_days[activity['id']] > current_day:
                        actual_completion_days[activity['id']] = current_day
                    elif activity['id'] in actual_completion_days and actual_completion_days[activity['id']] >= current_day:
                        del actual_completion_days[activity['id']]
                
                # Calculate actual manpower cost based on available manpower
                manpower_in_other_site = int(request.form.get(f"manpower_idle_{activity['id']}", 0))
                available_manpower = activity['planned_manpower'] - manpower_in_other_site
                manpower_ratio = available_manpower / activity['planned_manpower']
                
                # Store both original and actual manpower costs
                activity['original_manpower_cost_per_day'] = activity['manpower_cost_per_day']
                activity['actual_manpower_cost_per_day'] = round(activity['manpower_cost_per_day'] * manpower_ratio, 2)
                activity['manpower_cost_per_day'] = activity['actual_manpower_cost_per_day']  # Update for display
                
                # Get equipment type and cost
                equipment_type = request.form.get(f"equipment_type_{activity['id']}", 'owned')
                activity['equipment_type'] = equipment_type
                equipment_cost = get_equipment_cost(activity, equipment_type)
                
                # Calculate base daily cost (ensure proper addition)
                activity['base_delay_cost_per_day'] = round(activity['actual_manpower_cost_per_day'] + equipment_cost, 2)
                
                # Update total delay cost based on critical path status
                if is_activity_critical(activity, critical_paths):
                    activity['total_delay_cost_per_day'] = round(activity['base_delay_cost_per_day'] + activity['site_overhead_cost_per_day'], 2)
                elif is_activity_close_to_critical(activity, critical_paths) and activity.get('is_delayed', False):
                    activity['total_delay_cost_per_day'] = round(activity['base_delay_cost_per_day'] + (activity['site_overhead_cost_per_day'] * 0.5), 2)
                else:
                    activity['total_delay_cost_per_day'] = activity['base_delay_cost_per_day']
            
            # Recalculate critical paths after activity updates
            critical_paths, project_duration = get_critical_path(activities)
            
            # Update delay costs based on critical path status and project extension
            update_activity_delay_costs(activities, critical_paths, current_day)

            summary = []
            for activity in activities:
                status = get_status(activity['id'], actual_completion_days, current_day)
                actual_finish = actual_completion_days.get(activity['id'])
                planned_finish = get_planned_finish_day(activity, activities, actual_completion_days)
                
                # Get equipment type from form, default to owned
                equipment_type = request.form.get(f"equipment_type_{activity['id']}", 'owned')
                equipment_cost = get_equipment_cost(activity, equipment_type)
                
                per_day_cost = activity['manpower_cost_per_day'] + equipment_cost
                planned_cost = activity['duration'] * per_day_cost
                delay_days = 0
                actual_cost = planned_cost
                delay_cost = 0
                if actual_finish is not None:
                    delay_days = max(0, actual_finish - planned_finish)
                    # Check if activity has free float and is within it
                    free_float = activity.get('free_float', 0)
                    remaining_free_float = max(0, free_float - delay_days) if delay_days > 0 else free_float
                    activity['remaining_free_float'] = remaining_free_float
                    
                    # Calculate costs based on free float
                    if free_float > 0 and delay_days <= free_float:
                        # If within free float, no cost overrun
                        actual_cost = planned_cost
                        delay_cost = 0
                        activity['is_within_free_float'] = True
                    else:
                        # Only calculate cost overrun if beyond free float or no free float
                        effective_delay_days = max(0, delay_days - free_float) if free_float > 0 else delay_days
                        actual_cost = (activity['duration'] + effective_delay_days) * per_day_cost
                        delay_cost = actual_cost - planned_cost
                        activity['is_within_free_float'] = False

                summary.append({
                    **activity,
                    "status": status,
                    "actual_completion_day": actual_finish if actual_finish is not None else "-",
                    "planned_finish_day": planned_finish,
                    "delay_days": delay_days,
                    "planned_cost": planned_cost,
                    "actual_cost": actual_cost,
                    "delay_cost": delay_cost,
                    "equipment_type": equipment_type,
                    "total_float": activity.get('total_float', 0),
                    "free_float": activity.get('free_float', 0),
                    "remaining_free_float": activity.get('remaining_free_float', activity.get('free_float', 0)),
                    "is_within_free_float": activity.get('is_within_free_float', False)
                })

            ready_activities = get_ready_activities(activities, actual_completion_days, current_day)
            
            # Find best sequence for parallel activities
            best_sequence, min_cost, sequence_options = find_best_sequence(ready_activities, current_day)
            
            # Get parallel groups
            parallel_groups = get_parallel_activities(ready_activities, current_day)
            
            # Calculate max delay cost for normalization
            max_delay_cost = max((a.get('total_delay_cost_per_day', 0) for a in ready_activities), default=1)
            
            # Update activity scores based on best sequence
            for activity in ready_activities:
                is_first_in_parallel = activity['id'] == best_sequence[0] if best_sequence else False
                activity['is_first_in_parallel'] = is_first_in_parallel
                
                # Get updated constraints from form with error handling
                try:
                    # First get manpower in other site
                    manpower_in_other_site = int(request.form.get(f"manpower_idle_{activity['id']}", 0))
                    activity['manpower_in_other_site'] = manpower_in_other_site
                    
                    # Then calculate available manpower based on planned manpower and manpower in other site
                    available_manpower = activity['planned_manpower'] - manpower_in_other_site
                    activity['available_manpower'] = max(0, available_manpower)  # Ensure it doesn't go below 0
                except (ValueError, TypeError):
                    activity['manpower_in_other_site'] = 0
                    activity['available_manpower'] = activity['planned_manpower']
                    
                try:
                    # Handle material availability
                    material_type = request.form.get(f"material_type_{activity['id']}", '100')
                    if material_type == '0':
                        activity['material'] = 0.0  # Not Available
                    elif material_type == '100':
                        activity['material'] = 1.0  # 100% Available
                    else:  # Custom percentage
                        try:
                            percentage = float(request.form.get(f"material_percentage_{activity['id']}", 100))
                            activity['material'] = max(0.0, min(1.0, percentage / 100))  # Convert to 0-1 range
                        except (ValueError, TypeError):
                            activity['material'] = 1.0  # Default to 100% if invalid input
                except Exception as e:
                    print(f"Error processing material availability: {e}")
                    activity['material'] = 1.0  # Default to 100% if any error
                    
                # Get equipment type from form, default to owned
                activity['equipment_type'] = request.form.get(f"equipment_type_{activity['id']}", 'owned')
                
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
                
                # Add critical paths to activity context
                activity['critical_paths'] = critical_paths
                
                # Calculate score with detailed breakdown
                score_details = calculate_score(
                    activity['material'],  # material
                    activity['equipment_type'],  # equipment type
                    manpower_ratio,  # manpower_ratio
                    activity['delay_cost_per_day'],
                    max_delay_cost,
                    is_first_in_parallel,
                    activity,
                    activities  # Pass the activities list as all_activities
                )
                
                # Add score details to activity
                activity.update(score_details)
                
                # Add parallel group information
                activity['parallel_group'] = None
                for group in parallel_groups:
                    if activity in group:
                        activity['parallel_group'] = [a for a in group]
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
                
                # Calculate costs based on equipment type
                equipment_cost = get_equipment_cost(activity, activity['equipment_type'])
                per_day_cost = activity['manpower_cost_per_day'] + equipment_cost
                activity['planned_cost'] = activity['duration'] * per_day_cost
                activity['delay_cost'] = 0

            # Sort activities by score
            ready_activities.sort(key=lambda x: x.get('total_score', 0), reverse=True)
            prev_ready_ids = ','.join([a['id'] for a in ready_activities])
            session['actual_completion_days'] = actual_completion_days

            sidebar_options = ["Project Overview", "CPM Schedule", "Cost Analysis", "Settings"]

            cpm_mermaid = build_cpm_mermaid(activities)
            daywise_costs = build_daywise_costs(activities, summary, total_duration)

            # Before rendering the template, ensure all_activities have float values
            activities = get_float_values(activities)

            # --- FINAL: Delay score based on base_delay_cost_per_day in parallel group (user requirement, no zeroing for first activity) ---
            for activity in ready_activities:
                if 'sequence_options' in activity:
                    for option in activity['sequence_options']:
                        group_acts = option['activities']
                        delay_costs_for_score = []
                        
                        # First pass: collect all delay costs
                        for act in group_acts:
                            actual_act = next((a for a in ready_activities if a['id'] == act['id']), None)
                            if actual_act:
                                delay_cost = actual_act.get('total_delay_cost_per_day', 0)
                                actual_act['delay_cost_for_score'] = delay_cost
                                delay_costs_for_score.append(delay_cost)
                        
                        # Find max delay cost
                        max_delay_cost_for_score = max(delay_costs_for_score) if delay_costs_for_score else 1
                        
                        # Second pass: calculate scores
                        for act in group_acts:
                            actual_act = next((a for a in ready_activities if a['id'] == act['id']), None)
                            if actual_act:
                                if actual_act.get('delay_cost_for_score', 0) == 0:
                                    actual_act['delay_score'] = 0
                                else:
                                    actual_act['delay_score'] = round((actual_act['delay_cost_for_score'] / max_delay_cost_for_score) * 35, 2)
                                print(f"Activity {actual_act['id']}: delay_cost={actual_act['delay_cost_for_score']}, max_delay_cost={max_delay_cost_for_score}, score={actual_act['delay_score']}")

            return render_template('index.html', activities=ready_activities, updated=True, current_day=current_day,
                                   actual_completion_days=actual_completion_days, all_activities=activities,
                                   total_duration=total_duration, prev_ready=prev_ready_ids, summary=summary,
                                   sidebar_options=sidebar_options, cpm_mermaid=cpm_mermaid, daywise_costs=daywise_costs,
                                   parallel_groups=parallel_groups, owner_name="Patchikolla Preetham Sai",
                                   critical_paths=critical_paths, project_duration=project_duration)

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
                activity['manpower_in_other_site'] = 0
                activity['available_manpower'] = activity['planned_manpower']
                activity['material'] = 1.0  # Default to 100% available
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
                    is_first_in_parallel,
                    activity,
                    activities  # Pass the activities list as all_activities
                )
                
                # Add score details to activity
                activity.update(score_details)
                
                # Add parallel group information
                activity['parallel_group'] = None
                for group in parallel_groups:
                    if activity in group:
                        activity['parallel_group'] = [a for a in group]
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
                    activity['manpower_cost_per_day'] +
                    activity['rented_equipment_cost_per_day']
                )
                activity['planned_cost'] = activity['duration'] * per_day_cost
                activity['delay_cost'] = 0

            ready_activities.sort(key=lambda x: x.get('total_score', 0), reverse=True)
            prev_ready_ids = ','.join([a['id'] for a in ready_activities])

            summary = []
            for activity in activities:
                status = get_status(activity['id'], actual_completion_days, current_day)
                actual_finish = actual_completion_days.get(activity['id'])
                planned_finish = get_planned_finish_day(activity, activities, actual_completion_days)
                
                # Get equipment type from form, default to owned
                equipment_type = request.form.get(f"equipment_type_{activity['id']}", 'owned')
                equipment_cost = get_equipment_cost(activity, equipment_type)
                
                per_day_cost = activity['manpower_cost_per_day'] + equipment_cost
                planned_cost = activity['duration'] * per_day_cost
                delay_days = 0
                actual_cost = planned_cost
                delay_cost = 0
                if actual_finish is not None:
                    delay_days = max(0, actual_finish - planned_finish)
                    # Check if activity has free float and is within it
                    free_float = activity.get('free_float', 0)
                    remaining_free_float = max(0, free_float - delay_days) if delay_days > 0 else free_float
                    activity['remaining_free_float'] = remaining_free_float
                    
                    # Calculate costs based on free float
                    if free_float > 0 and delay_days <= free_float:
                        # If within free float, no cost overrun
                        actual_cost = planned_cost
                        delay_cost = 0
                        activity['is_within_free_float'] = True
                    else:
                        # Only calculate cost overrun if beyond free float or no free float
                        effective_delay_days = max(0, delay_days - free_float) if free_float > 0 else delay_days
                        actual_cost = (activity['duration'] + effective_delay_days) * per_day_cost
                        delay_cost = actual_cost - planned_cost
                        activity['is_within_free_float'] = False

                summary.append({
                    **activity,
                    "status": status,
                    "actual_completion_day": actual_finish if actual_finish is not None else "-",
                    "planned_finish_day": planned_finish,
                    "delay_days": delay_days,
                    "planned_cost": planned_cost,
                    "actual_cost": actual_cost,
                    "delay_cost": delay_cost,
                    "equipment_type": equipment_type,
                    "total_float": activity.get('total_float', 0),
                    "free_float": activity.get('free_float', 0),
                    "remaining_free_float": activity.get('remaining_free_float', activity.get('free_float', 0)),
                    "is_within_free_float": activity.get('is_within_free_float', False)
                })

            sidebar_options = ["Project Overview", "CPM Schedule", "Cost Analysis", "Settings"]

            cpm_mermaid = build_cpm_mermaid(activities)
            daywise_costs = build_daywise_costs(activities, summary, total_duration)

            # Before rendering the template, ensure all_activities have float values
            activities = get_float_values(activities)

            # --- FINAL: Delay score based on base_delay_cost_per_day in parallel group (user requirement, no zeroing for first activity) ---
            for activity in ready_activities:
                if 'sequence_options' in activity:
                    for option in activity['sequence_options']:
                        group_acts = option['activities']
                        delay_costs_for_score = []
                        
                        # First pass: collect all delay costs
                        for act in group_acts:
                            actual_act = next((a for a in ready_activities if a['id'] == act['id']), None)
                            if actual_act:
                                delay_cost = actual_act.get('total_delay_cost_per_day', 0)
                                actual_act['delay_cost_for_score'] = delay_cost
                                delay_costs_for_score.append(delay_cost)
                        
                        # Find max delay cost
                        max_delay_cost_for_score = max(delay_costs_for_score) if delay_costs_for_score else 1
                        
                        # Second pass: calculate scores
                        for act in group_acts:
                            actual_act = next((a for a in ready_activities if a['id'] == act['id']), None)
                            if actual_act:
                                if actual_act.get('delay_cost_for_score', 0) == 0:
                                    actual_act['delay_score'] = 0
                                else:
                                    actual_act['delay_score'] = round((actual_act['delay_cost_for_score'] / max_delay_cost_for_score) * 35, 2)
                                print(f"Activity {actual_act['id']}: delay_cost={actual_act['delay_cost_for_score']}, max_delay_cost={max_delay_cost_for_score}, score={actual_act['delay_score']}")

            return render_template('index.html', activities=ready_activities, updated=False, current_day=current_day,
                                   actual_completion_days=actual_completion_days, all_activities=activities,
                                   total_duration=total_duration, prev_ready=prev_ready_ids, summary=summary,
                                   sidebar_options=sidebar_options, cpm_mermaid=cpm_mermaid, daywise_costs=daywise_costs,
                                   parallel_groups=parallel_groups, owner_name="Patchikolla Preetham Sai",
                                   critical_paths=critical_paths, project_duration=project_duration)
    except Exception as e:
        print(f"Error in index route: {e}")
        return "An error occurred. Please try again.", 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)