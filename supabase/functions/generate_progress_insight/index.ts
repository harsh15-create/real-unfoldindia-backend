import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

serve(async (req) => {
    if (req.method === 'OPTIONS') {
        return new Response('ok', { headers: corsHeaders });
    }

    try {
        const supabaseClient = createClient(
            Deno.env.get('SUPABASE_URL') ?? '',
            Deno.env.get('SUPABASE_ANON_KEY') ?? '',
            { global: { headers: { Authorization: req.headers.get('Authorization')! } } }
        );

        const {
            india_progress,
            region_progress,
            explored_regions,
            unexplored_regions,
            top_travel_styles,
            unlocked_badges,
            insight_type = 'summary'
        } = await req.json();

        // 1. Generate Input Hash to prevent duplicate calls
        const inputString = JSON.stringify({
            india_progress,
            region_progress,
            explored_regions,
            unexplored_regions,
            top_travel_styles,
            unlocked_badges,
            insight_type
        });

        // Simple hash function for demo purposes (in prod use crypto.subtle)
        let hash = 0;
        for (let i = 0; i < inputString.length; i++) {
            const char = inputString.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash; // Convert to 32bit integer
        }
        const inputHash = hash.toString();

        // 2. Check Cache
        const { data: { user } } = await supabaseClient.auth.getUser();
        if (!user) throw new Error('Unauthorized');

        const { data: cachedInsight } = await supabaseClient
            .from('user_progress_insights')
            .select('*')
            .eq('user_id', user.id)
            .eq('input_hash', inputHash)
            .eq('insight_type', insight_type)
            .single();

        if (cachedInsight) {
            let parsedCache;
            try {
                parsedCache = JSON.parse(cachedInsight.output_text);
            } catch {
                parsedCache = { insight: cachedInsight.output_text };
            }
            return new Response(JSON.stringify({ ...parsedCache, cached: true }), {
                headers: { ...corsHeaders, 'Content-Type': 'application/json' },
            });
        }

        // 3. Call Groq API
        const GROQ_API_KEY = Deno.env.get('GROQ_API_KEY');
        if (!GROQ_API_KEY) {
            throw new Error('GROQ_API_KEY is not set');
        }

        // Construct Prompt
        const systemPrompt = `You are Kira, an elite travel AI for Unfold India. 
        Your goal is to analyze the user's travel profile and generate a personalized, structured insight.
        
        **INPUT DATA:**
        - India Explored %
        - Travel Styles (e.g., Adventure, Luxury)
        - Unlocked Badges
        - Unexplored Regions

        **OUTPUT FORMAT:**
        You must return a valid JSON object with these keys:
        {
            "insight": "A 2-sentence personalized message. Reference their specific travel style or recent badges.",
            "focus_area": "A specific region or city to target next (e.g., 'South India' or 'Rishikesh').",
            "next_milestone": "The next logical badge or goal (e.g., 'Unlock Explorer Badge').",
            "action_tip": "A short, punchy action (e.g., 'Plan a trip to Kerala')."
        }

        **TONE:**
        - Professional yet encouraging.
        - If they like 'Adventure', suggest thrilling spots.
        - If they like 'Luxury', suggest royal/comfort spots.
        - Mention their badges to gamify the experience.
        `;

        const userPrompt = `
        User Stats:
        - India Explored: ${india_progress}%
        - Travel Styles: ${top_travel_styles.join(', ') || 'General'}
        - Unlocked Badges: ${unlocked_badges.join(', ') || 'None'}
        - Unexplored Regions: ${unexplored_regions.join(', ')}
        
        Generate the JSON insight.`;

        const response = await fetch('https://api.groq.com/openai/v1/chat/completions', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${GROQ_API_KEY}`,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                model: 'llama-3.1-8b-instant',
                messages: [
                    { role: 'system', content: systemPrompt },
                    { role: 'user', content: userPrompt }
                ],
                temperature: 0.7,
                max_tokens: 200,
                response_format: { type: "json_object" }
            }),
        });

        const aiData = await response.json();

        if (!response.ok) {
            console.error('Groq API Error:', aiData);
            throw new Error(aiData.error?.message || 'Failed to fetch insight from Groq');
        }

        const rawContent = aiData.choices[0]?.message?.content;
        let parsedContent;
        try {
            parsedContent = JSON.parse(rawContent);
        } catch (e) {
            console.error("Failed to parse AI JSON:", rawContent);
            // Fallback
            parsedContent = {
                insight: rawContent || "Keep exploring to unlock more insights!",
                focus_area: "India",
                next_milestone: "Explorer Badge",
                action_tip: "Explore more cities"
            };
        }

        // 4. Save to Cache (Store the full JSON object as text)
        await supabaseClient.from('user_progress_insights').insert({
            user_id: user.id,
            insight_type,
            input_hash: inputHash,
            output_text: JSON.stringify(parsedContent)
        });

        return new Response(JSON.stringify({ ...parsedContent, cached: false }), {
            headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        });



    } catch (error) {
        return new Response(JSON.stringify({ error: error.message }), {
            status: 400,
            headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        });
    }
});
