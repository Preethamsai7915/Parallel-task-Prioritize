from flask import Flask, render_template, request, session, redirect, url_for
import os
import csv
from itertools import permutations
from datetime import datetime, timedelta
import json
import copy

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your_secret_key')

# Ensure the application is in production mode
app.config['ENV'] = 'production'
app.config['DEBUG'] = False

# Project start date - this will be the reference date for all calculations
PROJECT_START_DATE = datetime(2025, 7, 1)

def date_to_project_day(date_str):
    """Convert a date string (YYYY-MM-DD) to project day number"""
    if not date_str:
        return 1
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        delta = date_obj - PROJECT_START_DATE
        return delta.days + 1
    except:
        return 1

def project_day_to_date(project_day):
    """Convert project day number to date string (YYYY-MM-DD)"""
    try:
        date_obj = PROJECT_START_DATE + timedelta(days=project_day - 1)
        return date_obj.strftime('%Y-%m-%d')
    except:
        return PROJECT_START_DATE.strftime('%Y-%m-%d')

def get_current_date_from_project_day(project_day):
    """Get current date string from project day"""
    return project_day_to_date(project_day)

def get_project_day_from_date(date_str):
    """Get project day from date string"""
    return date_to_project_day(date_str)

def load_activities():
    activities = []
    try:
        with open('activities.csv', 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                # Convert string values to appropriate types
                activity = {
                    'id': row['id'],
                    'name': row['name'],
                    'duration': int(row['duration']),
                    'planned_manpower': int(row['planned_manpower']),
                    'skilled_manpower': int(row['skilled_manpower']),
                    'semi_skilled_manpower': int(row['semi_skilled_manpower']),
                    'unskilled_manpower': int(row['unskilled_manpower']),
                    'skilled_cost_per_day': int(row['skilled_cost_per_day']),
                    'semi_skilled_cost_per_day': int(row['semi_skilled_cost_per_day']),
                    'unskilled_cost_per_day': int(row['unskilled_cost_per_day']),
                    'start_day': int(row['start_day']),
                    'dependency_ids': row['dependency_ids'].split(',') if row['dependency_ids'] else [],
                    'manpower_cost_per_day': int(row['manpower_cost_per_day']),
                    'rented_equipment_cost_per_day': int(row['rented_equipment_cost_per_day']),
                    'owned_equipment_om_cost_per_day': int(row['owned_equipment_om_cost_per_day']),
                    'no_equipment_cost_per_day': int(row['no_equipment_cost_per_day']),
                    'total_delay_cost_per_day': int(row['total_delay_cost_per_day']),
                    'site_overhead_cost_per_day': int(row['site_overhead_cost_per_day']),
                    'planned_start_date': row.get('planned_start_date', ''),
                    'planned_end_date': row.get('planned_end_date', ''),
                    'actual_start_date': row.get('actual_start_date', ''),
                    'actual_end_date': row.get('actual_end_date', '')
                }
                
                # Calculate planned start and end dates if not provided
                if not activity['planned_start_date']:
                    activity['planned_start_date'] = project_day_to_date(activity['start_day'])
                if not activity['planned_end_date']:
                    activity['planned_end_date'] = project_day_to_date(activity['start_day'] + activity['duration'] - 1)
                
                activities.append(activity)
    except Exception as e:
        print(f"Error loading activities: {e}")
        # Return sample data if file not found
        activities = [
            {
                'id': 'A1', 'name': 'Site Survey and Layout', 'duration': 2, 'planned_manpower': 8,
                'skilled_manpower': 3, 'semi_skilled_manpower': 3, 'unskilled_manpower': 2,
                'skilled_cost_per_day': 300, 'semi_skilled_cost_per_day': 200, 'unskilled_cost_per_day': 100,
                'start_day': 1, 'dependency_ids': [], 'manpower_cost_per_day': 2100,
                'rented_equipment_cost_per_day': 1500, 'owned_equipment_om_cost_per_day': 500,
                'no_equipment_cost_per_day': 0, 'total_delay_cost_per_day': 2600, 'site_overhead_cost_per_day': 500,
                'planned_start_date': '2024-01-01', 'planned_end_date': '2024-01-02',
                'actual_start_date': '', 'actual_end_date': ''
            }
        ]
    # Ensure every activity has weights and score fields
    for activity in activities:
        if 'weights' not in activity:
            activity['weights'] = {
                'delay': 0,
                'equipment': 0,
                'manpower': 0,
                'material': 0,
                'critical_path': 0
            }
        for key in ['delay_score', 'equipment_score', 'manpower_score', 'material_score', 'critical_path_score', 'total_score']:
            if key not in activity:
                activity[key] = 0
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
            equipment_type = activity.get('equipment_type', 'owned')
            score_details = calculate_score(
                activity.get('material', 1.0),  # material
                equipment_type,  # equipment type
                min(1.0, activity.get('available_manpower', activity['planned_manpower']) / activity['planned_manpower']) if activity['planned_manpower'] > 0 else 0,  # manpower_ratio
                activity['total_delay_cost_per_day'] if not is_first else 0,
                max_delay_cost,
                is_first,
                activity,
                None  # Remove all_activities to prevent circular reference
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

def is_activity_critical(activity, critical_path):
    """Check if an activity is on the main critical path."""
    try:
        # Define the main critical path sequence
        critical_path_sequence = [
            'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7', 'A8', 'A9', 'A10',
            'A11', 'A12', 'A13', 'A14', 'A15', 'A16', 'A17', 'A18', 'A19', 'A20',
            'A21', 'A22', 'A23', 'A24', 'A25', 'A26', 'A27', 'A28', 'A29', 'A30',
            'A31', 'A32', 'A33', 'A34', 'A35', 'A36', 'A37', 'A38', 'A39', 'A40',
            'A118', 'A119', 'A120', 'A121', 'A122'
        ]
        
        # Check if the activity is in the critical path sequence
        return activity['id'] in critical_path_sequence
    except Exception as e:
        print(f"Error checking if activity is critical: {e}")
        return False

def is_activity_close_to_critical(activity, critical_path, threshold=2):
    """Check if an activity is close to the main critical path within a threshold."""
    try:
        # Define the main critical path sequence
        critical_path_sequence = [
            'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7', 'A8', 'A9', 'A10',
            'A11', 'A12', 'A13', 'A14', 'A15', 'A16', 'A17', 'A18', 'A19', 'A20',
            'A21', 'A22', 'A23', 'A24', 'A25', 'A26', 'A27', 'A28', 'A29', 'A30',
            'A31', 'A32', 'A33', 'A34', 'A35', 'A36', 'A37', 'A38', 'A39', 'A40',
            'A118', 'A119', 'A120', 'A121', 'A122'
        ]
        
        # Check if activity is directly connected to any critical path activity
        for critical_activity_id in critical_path_sequence:
            # Check if activity is a dependency of critical activity
            if critical_activity_id in activity.get('dependency_ids', []):
                return True
            # Check if critical activity is a dependency of this activity
            if activity['id'] in critical_activity_id:
                return True
            # Check if they share dependencies
            # This would require looking up the critical activity's dependencies
            # For simplicity, we'll check if this activity has any dependencies that are critical
            for dep in activity.get('dependency_ids', []):
                if dep in critical_path_sequence:
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
            equipment_type = activity.get('equipment_type', 'owned')
            equipment_cost = get_equipment_cost(activity, equipment_type)
            
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
                # Simplified delay score calculation to avoid circular references
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
                    # For non-parallel activities, use a simpler approach
                    current_delay_cost = activity.get('total_delay_cost_per_day', 0)
                    if current_delay_cost > 0:
                        # If there's a delay cost, give proportional score
                        delay_score = min(35, current_delay_cost / 1000 * 35)  # Normalize to reasonable range
                    else:
                        # No delay cost, give full score
                        delay_score = 35

        # Calculate equipment score (25%)
        equipment_score = 0
        if activity:
            equipment_type = activity.get('equipment_type', 'owned')
            if equipment_type == 'rented':
                equipment_score = 25  # Full score for rented equipment
            elif equipment_type == 'owned':
                # Calculate score based on relative cost
                rented_cost = activity.get('rented_equipment_cost_per_day', 0)
                owned_cost = activity.get('owned_equipment_om_cost_per_day', 0)
                if rented_cost > 0:
                    # Score is proportional to owned cost relative to rented cost
                    equipment_score = (owned_cost / rented_cost) * 25
                else:
                    equipment_score = 0
            elif equipment_type == 'no_equipment':
                equipment_score = 0  # Zero score for no equipment
            else:
                equipment_score = 0  # Default to zero score for any other case

        # Calculate manpower score (15%) - broken down by worker type
        # 7% for skilled, 5% for semi-skilled, 3% for unskilled
        manpower_score = 0
        if activity:
            # Calculate individual ratios for each worker type
            skilled_ratio = 0
            semi_skilled_ratio = 0
            unskilled_ratio = 0
            
            if activity['skilled_manpower'] > 0:
                skilled_ratio = min(1.0, activity.get('available_skilled', activity['skilled_manpower']) / activity['skilled_manpower'])
            
            if activity['semi_skilled_manpower'] > 0:
                semi_skilled_ratio = min(1.0, activity.get('available_semi_skilled', activity['semi_skilled_manpower']) / activity['semi_skilled_manpower'])
            
            if activity['unskilled_manpower'] > 0:
                unskilled_ratio = min(1.0, activity.get('available_unskilled', activity['unskilled_manpower']) / activity['unskilled_manpower'])
            
            # Calculate weighted score: 7% skilled + 5% semi-skilled + 3% unskilled
            manpower_score = (skilled_ratio * 7) + (semi_skilled_ratio * 5) + (unskilled_ratio * 3)
        else:
            # Fallback to original calculation if no activity details available
            manpower_score = manpower_ratio * 15

        # Calculate material score (10%)
        material_score = material * 10

        # Calculate critical path score (15%)
        critical_path_score = 0
        if activity:
            # Get critical paths from the activity's context
            critical_path = activity.get('critical_paths', [])
            
            # Check if this activity is on any critical path
            if is_activity_critical(activity, critical_path):
                critical_path_score = 15
            # Check if activity is close to critical path
            elif is_activity_close_to_critical(activity, critical_path):
                critical_path_score = 10
            elif activity.get('parallel_group'):
                # Check if all activities in parallel group are critical
                all_critical = True
                for parallel_activity in activity['parallel_group']:
                    if not is_activity_critical(parallel_activity, critical_path):
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
        
        # Get critical path for highlighting
        critical_path, _ = get_critical_path(activities)
        critical_activities = set()
        if critical_path:
            for activity in critical_path[0]:
                critical_activities.add(activity['id'])
        
        # Define phases with better organization and visual grouping
        phases = {
            'Foundation': {
                'activities': ['A1', 'A2', 'A3', 'A4'],
                'color': '#e3f2fd',
                'border': '#1976d2'
            },
            'Basements': {
                'activities': ['A5', 'A6', 'A7', 'A8', 'A9', 'A10', 'A11', 'A12', 'A13', 'A14', 'A15', 'A16'],
                'color': '#f3e5f5',
                'border': '#7b1fa2'
            },
            'Ground Floor': {
                'activities': ['A17', 'A18', 'A19'],
                'color': '#e8f5e8',
                'border': '#388e3c'
            },
            'Floors 1-10': {
                'activities': ['A20', 'A21'],
                'color': '#fff3e0',
                'border': '#f57c00'
            },
            'Floors 11-20': {
                'activities': ['A22', 'A23'],
                'color': '#fff3e0',
                'border': '#f57c00'
            },
            'Floors 21-30': {
                'activities': ['A24', 'A25'],
                'color': '#fff3e0',
                'border': '#f57c00'
            },
            'Floors 31-40': {
                'activities': ['A26', 'A27'],
                'color': '#fff3e0',
                'border': '#f57c00'
            },
            'Floors 41-50': {
                'activities': ['A28', 'A29', 'A30', 'A31', 'A32', 'A33', 'A34', 'A35', 'A36', 'A37', 'A38', 'A39'],
                'color': '#fff3e0',
                'border': '#f57c00'
            },
            'Roof': {
                'activities': ['A40'],
                'color': '#fce4ec',
                'border': '#c2185b'
            },
            'MEP Systems': {
                'activities': ['A41', 'A42', 'A43', 'A44', 'A45', 'A46', 'A47', 'A48', 'A49', 'A50', 'A51', 'A52', 'A53', 'A54', 'A55', 'A56', 'A57', 'A58', 'A59', 'A60', 'A61', 'A62', 'A63', 'A64', 'A65', 'A66'],
                'color': '#e0f2f1',
                'border': '#00695c'
            },
            'Walls & Windows': {
                'activities': ['A67', 'A68', 'A69', 'A70', 'A71', 'A72', 'A73', 'A74', 'A75', 'A76', 'A77', 'A78', 'A79', 'A80'],
                'color': '#f1f8e9',
                'border': '#689f38'
            },
            'MEP Finishing': {
                'activities': ['A81', 'A82', 'A83', 'A84', 'A85', 'A86', 'A87', 'A88', 'A89', 'A90', 'A91', 'A92', 'A93', 'A94', 'A95', 'A96', 'A97', 'A98', 'A99', 'A100', 'A101', 'A102', 'A103'],
                'color': '#e0f2f1',
                'border': '#00695c'
            },
            'Finishing Works': {
                'activities': ['A104', 'A105', 'A106', 'A107', 'A108', 'A109', 'A110', 'A111', 'A112', 'A113', 'A114', 'A115', 'A116', 'A117'],
                'color': '#fff8e1',
                'border': '#fbc02d'
            },
            'Handover': {
                'activities': ['A118', 'A119', 'A120', 'A121', 'A122'],
                'color': '#e8eaf6',
                'border': '#3f51b5'
            }
        }
        
        # Create subgraph nodes for each phase with better styling
        for phase_name, phase_info in phases.items():
            phase_id = phase_name.replace(" ", "_").replace("-", "_").replace("&", "and")
            nodes.append(f'subgraph {phase_id}["{phase_name}"]')
            
            # Add activities in this phase
            for act in activities:
                if act['id'] in phase_info['activities']:
                    # Create better labels with activity info
                    if act['id'] in critical_activities:
                        # Critical path activities with special styling
                        label = f"{act['id']}\\n{act['name'][:25]}{'...' if len(act['name']) > 25 else ''}\\n{act['duration']}d"
                        nodes.append(f'    {act["id"]}["{label}"]:::critical')
                    else:
                        # Regular activities
                        label = f"{act['id']}\\n{act['name'][:25]}{'...' if len(act['name']) > 25 else ''}\\n{act['duration']}d"
                        nodes.append(f'    {act["id"]}["{label}"]:::normal')
            
            nodes.append('end')
        
        # Add edges between activities with better styling
        for act in activities:
            for dep in act['dependency_ids']:
                # Highlight critical path edges
                if act['id'] in critical_activities and dep in critical_activities:
                    edges.append(f'{dep} --> {act["id"]}:::criticalEdge')
                else:
                    edges.append(f'{dep} --> {act["id"]}:::normalEdge')
        
        # Create the mermaid diagram with enhanced styling
        mermaid_code = "flowchart LR\n"
        mermaid_code += "classDef critical fill:#ffebee,stroke:#d32f2f,stroke-width:3px,color:#000,font-weight:bold\n"
        mermaid_code += "classDef normal fill:#f5f5f5,stroke:#757575,stroke-width:1px,color:#000\n"
        mermaid_code += "classDef criticalEdge stroke:#d32f2f,stroke-width:3px\n"
        mermaid_code += "classDef normalEdge stroke:#757575,stroke-width:1px\n"
        mermaid_code += "\n".join(nodes) + "\n"
        mermaid_code += "\n".join(edges)
        
        return mermaid_code
    except Exception as e:
        print(f"Error building CPM mermaid: {e}")
        return "flowchart LR\nA1[Error building diagram]"

def get_critical_path(activities):
    try:
        # Define the main critical path sequence
        critical_path_sequence = [
            'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7', 'A8', 'A9', 'A10',
            'A11', 'A12', 'A13', 'A14', 'A15', 'A16', 'A17', 'A18', 'A19', 'A20',
            'A21', 'A22', 'A23', 'A24', 'A25', 'A26', 'A27', 'A28', 'A29', 'A30',
            'A31', 'A32', 'A33', 'A34', 'A35', 'A36', 'A37', 'A38', 'A39', 'A40',
            'A118', 'A119', 'A120', 'A121', 'A122'
        ]
        
        # Create a dictionary for easy activity lookup
        activity_dict = {act['id']: act for act in activities}
        
        # Build the critical path by following the sequence
        critical_path = []
        for activity_id in critical_path_sequence:
            if activity_id in activity_dict:
                critical_path.append(activity_dict[activity_id])
        
        print(f"Critical path built with {len(critical_path)} activities")
        print(f"Critical path activities: {[act['id'] for act in critical_path]}")
        
        # Calculate total duration
        total_duration = sum(act['duration'] for act in critical_path) if critical_path else 0
        print(f"Total critical path duration: {total_duration}")
        
        # Also calculate earliest start and finish times for all activities for float calculation
        earliest_start = {act['id']: 0 for act in activities}
        earliest_finish = {act['id']: 0 for act in activities}
        
        # Forward pass
        for act in activities:
            if not act['dependency_ids']:
                earliest_start[act['id']] = act['start_day']
            else:
                max_dep_finish = 0
                for dep in act['dependency_ids']:
                    if dep in earliest_finish:
                        max_dep_finish = max(max_dep_finish, earliest_finish[dep])
                earliest_start[act['id']] = max(max_dep_finish + 1, act['start_day'])
            earliest_finish[act['id']] = earliest_start[act['id']] + act['duration'] - 1
        
        # Calculate latest start and finish times
        project_duration = max(earliest_finish.values())
        latest_finish = {act['id']: project_duration for act in activities}
        latest_start = {act['id']: 0 for act in activities}
        
        # Create reverse dependency map
        reverse_deps = {}
        for act in activities:
            for dep in act['dependency_ids']:
                if dep not in reverse_deps:
                    reverse_deps[dep] = []
                reverse_deps[dep].append(act['id'])
        
        # Backward pass
        for act in reversed(activities):
            if act['id'] not in reverse_deps:
                latest_finish[act['id']] = project_duration
            else:
                min_succ_start = float('inf')
                for succ_id in reverse_deps[act['id']]:
                    if succ_id in latest_start:
                        min_succ_start = min(min_succ_start, latest_start[succ_id])
                latest_finish[act['id']] = min_succ_start - 1 if min_succ_start != float('inf') else project_duration
            
            latest_start[act['id']] = latest_finish[act['id']] - act['duration'] + 1
        
        # Update activities with float values
        for act in activities:
            act['early_start'] = earliest_start[act['id']]
            act['early_finish'] = earliest_finish[act['id']]
            act['late_start'] = latest_start[act['id']]
            act['late_finish'] = latest_finish[act['id']]
            act['total_float'] = latest_start[act['id']] - earliest_start[act['id']]
            
            # Calculate free float - ensure all successors have early_start set first
            successors = [a for a in activities if a.get('dependency_ids') and act['id'] in a['dependency_ids']]
            if successors:
                # Make sure all successors have early_start calculated
                for succ in successors:
                    if 'early_start' not in succ:
                        succ['early_start'] = earliest_start.get(succ['id'], 0)
                min_early_start = min(succ['early_start'] for succ in successors)
                act['free_float'] = min_early_start - act['early_finish'] - 1
            else:
                act['free_float'] = project_duration - act['early_finish']
            
            # Ensure floats are non-negative
            act['total_float'] = max(0, act['total_float'])
            act['free_float'] = max(0, act['free_float'])
            
            # Ensure all required attributes are present
            act.setdefault('free_float', 0)
            act.setdefault('total_float', 0)
            act.setdefault('early_start', 0)
            act.setdefault('early_finish', 0)
            act.setdefault('late_start', 0)
            act.setdefault('late_finish', 0)
            
            # Add critical path context to activity (fix NameError)
            if critical_path and critical_path[0]:
                act['critical_paths'] = [{'id': a['id']} for a in critical_path]
            else:
                act['critical_paths'] = []
        
        return [critical_path], total_duration
    except Exception as e:
        print(f"Error calculating critical path: {e}")
        import traceback
        traceback.print_exc()
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

def update_activity_delay_costs(activities, critical_path, current_day):
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
            is_critical = is_activity_critical(activity, critical_path)
            is_close_to_critical = is_activity_close_to_critical(activity, critical_path)
            
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

            # Add critical path context to activity (fix NameError)
            if critical_path and critical_path[0]:
                activity['critical_paths'] = [{'id': a['id']} for a in critical_path]
            else:
                activity['critical_paths'] = []
    except Exception as e:
        print(f"Error updating activity delay costs: {e}")

def optimize_for_large_project(activities, max_parallel_activities=10):
    """
    Optimize processing for large projects by limiting parallel activities
    """
    try:
        if len(activities) <= max_parallel_activities:
            return activities
        
        # For large projects, prioritize activities based on:
        # 1. Critical path activities
        # 2. Activities with highest delay costs
        # 3. Activities with earliest start dates
        
        # Sort activities by priority score
        for activity in activities:
            priority_score = 0
            
            # Critical path activities get highest priority
            if activity.get('is_critical', False):
                priority_score += 1000
            
            # Higher delay cost activities get higher priority
            priority_score += activity.get('total_delay_cost_per_day', 0)
            
            # Earlier start dates get higher priority
            priority_score += (1000 - activity.get('start_day', 1))
            
            activity['priority_score'] = priority_score
        
        # Sort by priority and return top activities
        sorted_activities = sorted(activities, key=lambda x: x.get('priority_score', 0), reverse=True)
        return sorted_activities[:max_parallel_activities]
    except Exception as e:
        print(f"Error optimizing for large project: {e}")
        return activities[:max_parallel_activities] if len(activities) > max_parallel_activities else activities

def build_cytoscape_elements(activities, critical_path=None):
    """
    Build Cytoscape.js elements (nodes and edges) for CPM visualization.
    Highlights critical path nodes and edges.
    """
    critical_ids = set()
    if critical_path and critical_path[0]:
        critical_ids = set(a['id'] for a in critical_path[0])
    nodes = []
    edges = []
    for act in activities:
        nodes.append({
            'data': {
                'id': act['id'],
                'label': f"{act['id']}\n{act['name'][:20]}{'...' if len(act['name']) > 20 else ''}\n{act['duration']}d"
            },
            'classes': 'critical' if act['id'] in critical_ids else ''
        })
        for dep in act['dependency_ids']:
            edges.append({
                'data': {'source': dep, 'target': act['id']},
                'classes': 'critical' if act['id'] in critical_ids and dep in critical_ids else ''
            })
    return nodes + edges

@app.route('/', methods=['GET', 'POST'])
def index():
    try:
        activities = load_activities()
        
        # Get actual completion days from session or default to empty dict
        actual_completion_days = session.get('actual_completion_days', {})
        # Get current project day from session or default to 1
        current_day = session.get('current_day', 1)
        # Calculate total project duration
        total_duration = get_total_duration(activities)
        
        # Handle date-based input
        if request.method == 'POST':
            # Check if we're getting a date input instead of project day
            current_date = request.form.get('current_date')
            if current_date:
                # Convert date to project day
                new_current_day = get_project_day_from_date(current_date)
                # If going to a previous date, remove all activities completed after that date
                if new_current_day < current_day:
                    # Filter out activities completed after the new current day
                    actual_completion_days = {k: v for k, v in actual_completion_days.items() if v <= new_current_day}
                    session['actual_completion_days'] = actual_completion_days
                current_day = new_current_day
            else:
                # Fallback to project day input
                new_current_day = int(request.form.get('current_day', 1))
                # If going to a previous day, remove all activities completed after that day
                if new_current_day < current_day:
                    # Filter out activities completed after the new current day
                    actual_completion_days = {k: v for k, v in actual_completion_days.items() if v <= new_current_day}
                    session['actual_completion_days'] = actual_completion_days
                current_day = new_current_day
            
            session['current_day'] = current_day
            
            # Get actual completion days from session (updated after filtering)
            actual_completion_days = session.get('actual_completion_days', {})
            
            # Handle activity completion updates
            for activity in activities:
                activity_id = activity['id']
                if f'complete_{activity_id}' in request.form:
                    # Mark activity as completed on current day
                    actual_completion_days[activity_id] = current_day
                elif f'uncomplete_{activity_id}' in request.form:
                    # Remove completion
                    if activity_id in actual_completion_days:
                        del actual_completion_days[activity_id]
            
            session['actual_completion_days'] = actual_completion_days
            
            # Get ready activities for current day
            ready_activities = get_ready_activities(activities, actual_completion_days, current_day)
            
            # Calculate critical paths and project duration for POST requests
            critical_paths, project_duration = get_critical_path(activities)
            
            # Optimize for large projects (110 activities)
            if len(ready_activities) > 10:
                ready_activities = optimize_for_large_project(ready_activities, max_parallel_activities=15)
                print(f"Large project optimization: Processing {len(ready_activities)} activities out of {len(get_ready_activities(activities, actual_completion_days, current_day))} total ready activities")
            
            # Find best sequence for parallel activities
            best_sequence, min_cost, sequence_options = find_best_sequence(ready_activities, current_day)
            
            # Get parallel groups
            parallel_groups = get_parallel_activities(ready_activities, current_day)
            
            # Update delay costs based on critical path status
            update_activity_delay_costs(activities, critical_paths, current_day)
            
            # Calculate max delay cost for normalization
            max_delay_cost = max((a.get('total_delay_cost_per_day', 0) for a in ready_activities), default=1)
            
            # Process form data for ALL activities
            for activity in activities:
                is_first_in_parallel = False
                if best_sequence:
                    is_first_in_parallel = activity['id'] == best_sequence[0]
                activity['is_first_in_parallel'] = is_first_in_parallel

                activity_id = activity['id']

                # Get manpower idle values
                skilled_idle = int(request.form.get(f'skilled_idle_{activity_id}', 0))
                semi_skilled_idle = int(request.form.get(f'semi_skilled_idle_{activity_id}', 0))
                unskilled_idle = int(request.form.get(f'unskilled_idle_{activity_id}', 0))

                # Calculate available manpower
                activity['skilled_idle'] = skilled_idle
                activity['semi_skilled_idle'] = semi_skilled_idle
                activity['unskilled_idle'] = unskilled_idle
                activity['available_skilled'] = max(0, activity['skilled_manpower'] - skilled_idle)
                activity['available_semi_skilled'] = max(0, activity['semi_skilled_manpower'] - semi_skilled_idle)
                activity['available_unskilled'] = max(0, activity['unskilled_manpower'] - unskilled_idle)
                activity['available_manpower'] = activity['available_skilled'] + activity['available_semi_skilled'] + activity['available_unskilled']

                # Get material availability
                material_type = request.form.get(f'material_type_{activity_id}', '100')
                if material_type == 'custom':
                    material_percentage = float(request.form.get(f'material_percentage_{activity_id}', 100))
                    activity['material'] = material_percentage / 100
                elif material_type == '0':
                    activity['material'] = 0
                else:
                    activity['material'] = 1.0

                # Get equipment type
                equipment_type = request.form.get(f'equipment_type_{activity_id}', 'owned')
                activity['equipment_type'] = equipment_type

                # Calculate actual manpower cost based on available manpower
                actual_skilled_cost = activity['available_skilled'] * activity['skilled_cost_per_day']
                actual_semi_skilled_cost = activity['available_semi_skilled'] * activity['semi_skilled_cost_per_day']
                actual_unskilled_cost = activity['available_unskilled'] * activity['unskilled_cost_per_day']
                activity['actual_manpower_cost_per_day'] = actual_skilled_cost + actual_semi_skilled_cost + actual_unskilled_cost

                # Get equipment type and cost
                equipment_cost = get_equipment_cost(activity, equipment_type)
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
                
                # Only calculate costs if activity was completed on or before current day
                if actual_finish is not None and actual_finish <= current_day:
                    # Calculate actual duration based on dependencies and early completion
                    actual_start = activity['start_day']
                    if activity['dependency_ids']:
                        dep_days = []
                        for dep in activity['dependency_ids']:
                            if dep in actual_completion_days and actual_completion_days[dep] <= current_day:
                                dep_days.append(actual_completion_days[dep])
                        if dep_days:
                            actual_start = max(max(dep_days) + 1, activity['start_day'])
                    
                    # Calculate actual duration
                    actual_duration = actual_finish - actual_start + 1
                    
                    # Calculate delay days
                    delay_days = max(0, actual_finish - planned_finish)
                    
                    # Check if activity has free float and is within it
                    free_float = activity.get('free_float', 0)
                    remaining_free_float = max(0, free_float - delay_days) if delay_days > 0 else free_float
                    activity['remaining_free_float'] = remaining_free_float
                    
                    # Calculate costs based on actual duration
                    if actual_duration < activity['duration']:
                        # Early completion - reduced cost
                        actual_cost = actual_duration * per_day_cost
                        delay_cost = 0
                        activity['is_within_free_float'] = True
                    elif free_float > 0 and delay_days <= free_float:
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
                else:
                    # Activity not completed or completed after current day - use planned values
                    actual_finish = None
                    delay_days = 0
                    actual_cost = planned_cost
                    delay_cost = 0
                    activity['remaining_free_float'] = activity.get('free_float', 0)
                    activity['is_within_free_float'] = True

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

            # Calculate scores for ready_activities (this was missing in POST request)
            for activity in ready_activities:
                is_first_in_parallel = activity['id'] == best_sequence[0] if best_sequence else False
                activity['is_first_in_parallel'] = is_first_in_parallel
                
                # Calculate manpower ratio
                total_planned_manpower = activity['skilled_manpower'] + activity['semi_skilled_manpower'] + activity['unskilled_manpower']
                manpower_ratio = min(1.0, activity['available_manpower'] / total_planned_manpower) if total_planned_manpower > 0 else 0
                
                # Calculate delay cost for this activity
                if not is_first_in_parallel:
                    delay_days = current_day - activity['start_day']
                    if delay_days > 0:
                        activity['delay_cost_per_day'] = activity['total_delay_cost_per_day']
                    else:
                        activity['delay_cost_per_day'] = 0
                else:
                    activity['delay_cost_per_day'] = 0
                
                # Calculate current delay for the activity
                current_delay = max(0, current_day - activity['start_day'])
                activity['current_delay'] = current_delay
                
                # Add critical paths context to activity
                activity['critical_paths'] = critical_paths
                
                # Get equipment type for scoring
                equipment_type = activity.get('equipment_type', 'owned')
                
                score_details = calculate_score(
                    activity['material'],  # material
                    equipment_type,  # equipment type (rented/owned/no_equipment)
                    manpower_ratio,  # manpower_ratio
                    activity['delay_cost_per_day'],
                    max((a.get('delay_cost_per_day', 0) for a in ready_activities), default=1),
                    is_first_in_parallel,
                    activity,
                    None  # Remove all_activities to prevent circular reference
                )
                
                # Add score details to activity
                activity.update(score_details)
                
                # Add parallel group information
                activity['parallel_group'] = None
                for group in parallel_groups:
                    if activity in group:
                        # Create copies of activities to avoid circular references
                        activity['parallel_group'] = [{'id': a['id'], 'name': a['name'], 'total_delay_cost_per_day': a.get('total_delay_cost_per_day', 0), 'free_float': a.get('free_float', 0), 'current_delay': a.get('current_delay', 0)} for a in group]
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

            # Sort ready_activities by score
            ready_activities.sort(key=lambda x: x.get('total_score', 0), reverse=True)

            cpm_mermaid = build_cpm_mermaid(activities)
            daywise_costs = build_daywise_costs(activities, summary, total_duration)

            # Calculate planned_cost for all_activities so it's available in the GoJS flowchart
            for activity in activities:
                equipment_type = request.form.get(f"equipment_type_{activity['id']}", 'owned')
                equipment_cost = get_equipment_cost(activity, equipment_type)
                per_day_cost = activity['manpower_cost_per_day'] + equipment_cost
                activity['planned_cost'] = activity['duration'] * per_day_cost
                
                # Add other fields needed for GoJS activity details
                activity['actual_cost'] = activity['planned_cost']  # Default to planned cost
                activity['delay_cost'] = 0  # Default to 0
                activity['status'] = get_status(activity['id'], actual_completion_days, current_day)
                
                # Calculate actual cost and delay cost if activity is completed
                actual_finish = actual_completion_days.get(activity['id'])
                if actual_finish is not None and actual_finish <= current_day:
                    planned_finish = get_planned_finish_day(activity, activities, actual_completion_days)
                    delay_days = max(0, actual_finish - planned_finish)
                    
                    # Calculate actual duration
                    actual_start = activity['start_day']
                    if activity['dependency_ids']:
                        dep_days = []
                        for dep in activity['dependency_ids']:
                            if dep in actual_completion_days and actual_completion_days[dep] <= current_day:
                                dep_days.append(actual_completion_days[dep])
                        if dep_days:
                            actual_start = max(max(dep_days) + 1, activity['start_day'])
                    
                    actual_duration = actual_finish - actual_start + 1
                    
                    # Check free float
                    free_float = activity.get('free_float', 0)
                    
                    if actual_duration < activity['duration']:
                        # Early completion
                        activity['actual_cost'] = actual_duration * per_day_cost
                        activity['delay_cost'] = 0
                    elif free_float > 0 and delay_days <= free_float:
                        # Within free float
                        activity['actual_cost'] = activity['planned_cost']
                        activity['delay_cost'] = 0
                    else:
                        # Beyond free float
                        effective_delay_days = max(0, delay_days - free_float) if free_float > 0 else delay_days
                        activity['actual_cost'] = (activity['duration'] + effective_delay_days) * per_day_cost
                        activity['delay_cost'] = activity['actual_cost'] - activity['planned_cost']
                else:
                    # Activity not completed or completed after current day - use planned values
                    activity['actual_cost'] = activity['planned_cost']
                    activity['delay_cost'] = 0

            prev_ready_ids = ','.join([a['id'] for a in ready_activities])

            cpm_cytoscape_elements = build_cytoscape_elements(activities, critical_paths)

            # Determine if project not started or no activities for the selected date
            no_activities_message = None
            selected_date = get_current_date_from_project_day(current_day)
            if current_day < 1 or selected_date < PROJECT_START_DATE.strftime('%Y-%m-%d'):
                no_activities_message = "Project not started yet."
            elif not ready_activities:
                no_activities_message = "No scheduled activities for this date."

            return render_template('index.html', activities=ready_activities, updated=True, current_day=current_day,
                                   current_date=get_current_date_from_project_day(current_day),
                                   actual_completion_days=actual_completion_days, all_activities=activities,
                                   total_duration=total_duration, prev_ready=prev_ready_ids, summary=summary,
                                   sidebar_options=sidebar_options, cpm_mermaid=cpm_mermaid, daywise_costs=daywise_costs,
                                   parallel_groups=parallel_groups, owner_name="Patchikolla Preetham Sai",
                                   critical_paths=critical_paths, project_duration=project_duration,
                                   cpm_cytoscape_elements=cpm_cytoscape_elements,
                                   project_day_to_date=project_day_to_date,
                                   no_activities_message=no_activities_message)

        else:
            # Don't reset session data on GET request, maintain current state
            ready_activities = get_ready_activities(activities, actual_completion_days, current_day)
            
            # Calculate critical paths and project duration for GET requests
            critical_paths, project_duration = get_critical_path(activities)
            
            # Optimize for large projects (110 activities)
            if len(ready_activities) > 10:
                ready_activities = optimize_for_large_project(ready_activities, max_parallel_activities=15)
                print(f"Large project optimization: Processing {len(ready_activities)} activities out of {len(get_ready_activities(activities, actual_completion_days, current_day))} total ready activities")
            
            # Find best sequence for parallel activities
            best_sequence, min_cost, sequence_options = find_best_sequence(ready_activities, current_day)
            
            # Get parallel groups
            parallel_groups = get_parallel_activities(ready_activities, current_day)
            
            for activity in ready_activities:
                is_first_in_parallel = activity['id'] == best_sequence[0] if best_sequence else False
                activity['is_first_in_parallel'] = is_first_in_parallel
                
                # Set default values
                activity['skilled_idle'] = 0
                activity['semi_skilled_idle'] = 0
                activity['unskilled_idle'] = 0
                activity['available_skilled'] = activity['skilled_manpower']
                activity['available_semi_skilled'] = activity['semi_skilled_manpower']
                activity['available_unskilled'] = activity['unskilled_manpower']
                activity['available_manpower'] = activity['planned_manpower']
                activity['material'] = 1.0  # Default to 100% available
                activity['equipment'] = True
                
                # Calculate manpower ratio
                total_planned_manpower = activity['skilled_manpower'] + activity['semi_skilled_manpower'] + activity['unskilled_manpower']
                manpower_ratio = min(1.0, activity['available_manpower'] / total_planned_manpower) if total_planned_manpower > 0 else 0
                
                # Calculate delay cost for this activity
                if not is_first_in_parallel:
                    delay_days = current_day - activity['start_day']
                    if delay_days > 0:
                        activity['delay_cost_per_day'] = activity['total_delay_cost_per_day']
                    else:
                        activity['delay_cost_per_day'] = 0
                else:
                    activity['delay_cost_per_day'] = 0
                
                # Calculate current delay for the activity
                current_delay = max(0, current_day - activity['start_day'])
                activity['current_delay'] = current_delay
                
                # Add critical paths context to activity
                activity['critical_paths'] = critical_paths
                
                # Get equipment type for scoring
                equipment_type = activity.get('equipment_type', 'owned')
                
                score_details = calculate_score(
                    activity['material'],  # material
                    equipment_type,  # equipment type (rented/owned/no_equipment)
                    manpower_ratio,  # manpower_ratio
                    activity['delay_cost_per_day'],
                    max((a.get('delay_cost_per_day', 0) for a in ready_activities), default=1),
                    is_first_in_parallel,
                    activity,
                    None  # Remove all_activities to prevent circular reference
                )
                
                # Add score details to activity
                activity.update(score_details)
                
                # Add parallel group information
                activity['parallel_group'] = None
                for group in parallel_groups:
                    if activity in group:
                        # Create copies of activities to avoid circular references
                        activity['parallel_group'] = [{'id': a['id'], 'name': a['name'], 'total_delay_cost_per_day': a.get('total_delay_cost_per_day', 0), 'free_float': a.get('free_float', 0), 'current_delay': a.get('current_delay', 0)} for a in group]
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
                
                # Only calculate costs if activity was completed on or before current day
                if actual_finish is not None and actual_finish <= current_day:
                    # Calculate actual duration based on dependencies and early completion
                    actual_start = activity['start_day']
                    if activity['dependency_ids']:
                        dep_days = []
                        for dep in activity['dependency_ids']:
                            if dep in actual_completion_days and actual_completion_days[dep] <= current_day:
                                dep_days.append(actual_completion_days[dep])
                        if dep_days:
                            actual_start = max(max(dep_days) + 1, activity['start_day'])
                    
                    # Calculate actual duration
                    actual_duration = actual_finish - actual_start + 1
                    
                    # Calculate delay days
                    delay_days = max(0, actual_finish - planned_finish)
                    
                    # Check if activity has free float and is within it
                    free_float = activity.get('free_float', 0)
                    remaining_free_float = max(0, free_float - delay_days) if delay_days > 0 else free_float
                    activity['remaining_free_float'] = remaining_free_float
                    
                    # Calculate costs based on actual duration
                    if actual_duration < activity['duration']:
                        # Early completion - reduced cost
                        actual_cost = actual_duration * per_day_cost
                        delay_cost = 0
                        activity['is_within_free_float'] = True
                    elif free_float > 0 and delay_days <= free_float:
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
                else:
                    # Activity not completed or completed after current day - use planned values
                    actual_finish = None
                    delay_days = 0
                    actual_cost = planned_cost
                    delay_cost = 0
                    activity['remaining_free_float'] = activity.get('free_float', 0)
                    activity['is_within_free_float'] = True

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

            # Calculate planned_cost for all_activities so it's available in the GoJS flowchart
            for activity in activities:
                equipment_type = request.form.get(f"equipment_type_{activity['id']}", 'owned')
                equipment_cost = get_equipment_cost(activity, equipment_type)
                per_day_cost = activity['manpower_cost_per_day'] + equipment_cost
                activity['planned_cost'] = activity['duration'] * per_day_cost
                
                # Add other fields needed for GoJS activity details
                activity['actual_cost'] = activity['planned_cost']  # Default to planned cost
                activity['delay_cost'] = 0  # Default to 0
                activity['status'] = get_status(activity['id'], actual_completion_days, current_day)
                
                # Calculate actual cost and delay cost if activity is completed
                actual_finish = actual_completion_days.get(activity['id'])
                if actual_finish is not None and actual_finish <= current_day:
                    planned_finish = get_planned_finish_day(activity, activities, actual_completion_days)
                    delay_days = max(0, actual_finish - planned_finish)
                    
                    # Calculate actual duration
                    actual_start = activity['start_day']
                    if activity['dependency_ids']:
                        dep_days = []
                        for dep in activity['dependency_ids']:
                            if dep in actual_completion_days and actual_completion_days[dep] <= current_day:
                                dep_days.append(actual_completion_days[dep])
                        if dep_days:
                            actual_start = max(max(dep_days) + 1, activity['start_day'])
                    
                    actual_duration = actual_finish - actual_start + 1
                    
                    # Check free float
                    free_float = activity.get('free_float', 0)
                    
                    if actual_duration < activity['duration']:
                        # Early completion
                        activity['actual_cost'] = actual_duration * per_day_cost
                        activity['delay_cost'] = 0
                    elif free_float > 0 and delay_days <= free_float:
                        # Within free float
                        activity['actual_cost'] = activity['planned_cost']
                        activity['delay_cost'] = 0
                    else:
                        # Beyond free float
                        effective_delay_days = max(0, delay_days - free_float) if free_float > 0 else delay_days
                        activity['actual_cost'] = (activity['duration'] + effective_delay_days) * per_day_cost
                        activity['delay_cost'] = activity['actual_cost'] - activity['planned_cost']
                else:
                    # Activity not completed or completed after current day - use planned values
                    activity['actual_cost'] = activity['planned_cost']
                    activity['delay_cost'] = 0

            cpm_cytoscape_elements = build_cytoscape_elements(activities, critical_paths)

            # Determine if project not started or no activities for the selected date
            no_activities_message = None
            selected_date = get_current_date_from_project_day(current_day)
            if current_day < 1 or selected_date < PROJECT_START_DATE.strftime('%Y-%m-%d'):
                no_activities_message = "Project not started yet."
            elif not ready_activities:
                no_activities_message = "No scheduled activities for this date."

            return render_template('index.html', activities=ready_activities, updated=False, current_day=current_day,
                                   current_date=get_current_date_from_project_day(current_day),
                                   actual_completion_days=actual_completion_days, all_activities=activities,
                                   total_duration=total_duration, prev_ready=prev_ready_ids, summary=summary,
                                   sidebar_options=sidebar_options, cpm_mermaid=cpm_mermaid, daywise_costs=daywise_costs,
                                   parallel_groups=parallel_groups, owner_name="Patchikolla Preetham Sai",
                                   critical_paths=critical_paths, project_duration=project_duration,
                                   cpm_cytoscape_elements=cpm_cytoscape_elements,
                                   project_day_to_date=project_day_to_date,
                                   no_activities_message=no_activities_message)
    except Exception as e:
        print(f"Error in index route: {e}")
        return "An error occurred. Please try again.", 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)