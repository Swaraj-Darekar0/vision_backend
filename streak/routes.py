from flask import Blueprint, request, jsonify
from supabase import create_client
import os
import random
import config

streak_bp = Blueprint('streak', __name__, url_prefix='/streak')

@streak_bp.route('/tip', methods=['GET'])
def get_streak_tip():
    """
    GET /streak/tip?milestone=<int>&skill=<string>
    Fetches a random motivational tip for a given streak milestone and skill focus.
    Source: backend_implementation_plan.md Task BE-T1-1.
    """
    milestone = request.args.get('milestone', type=int)
    skill = request.args.get('skill', type=str)

    # Valid milestones as per specification
    if milestone not in [3, 7, 14, 30] or not skill:
        return jsonify({'error': 'invalid params — milestone must be one of [3, 7, 14, 30] and skill must be provided'}), 400

    # Skills allowed (including 'overall')
    allowed_skills = ['confidence', 'clarity', 'engagement', 'nervousness', 'overall']
    if skill not in allowed_skills:
        return jsonify({'error': f'invalid skill focus — must be one of {allowed_skills}'}), 400

    try:
        # Initialize Supabase client
        supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
        
        # Query the table
        result = (
            supabase.table('motivational_tips')
            .select('tip_text')
            .eq('streak_milestone', milestone)
            .eq('skill_focus', skill)
            .execute()
        )

        rows = result.data
        if not rows:
            return jsonify({'tip_text': None}), 200

        # Choose a random tip if multiple exist
        tip = random.choice(rows)['tip_text']
        
        response = jsonify({
            'tip_text': tip, 
            'milestone': milestone, 
            'skill': skill
        })
        
        # Cache for 24 hours (86400 seconds)
        response.headers['Cache-Control'] = 'max-age=86400'
        return response

    except Exception as e:
        # Log error but don't crash the server
        return jsonify({'error': f'Internal Server Error: {str(e)}'}), 500
