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
            return new Response(JSON.stringify({ insight: cachedInsight.output_text, cached: true }), {
                headers: { ...corsHeaders, 'Content-Type': 'application/json' },
            });
        }

        // 3. Call Groq API
        const GROQ_API_KEY = Deno.env.get('GROQ_API_KEY');
        if (!GROQ_API_KEY) {
            throw new Error('GROQ_API_KEY is not set');
        }

        // Construct Prompt
        const systemPrompt = `You are Kira, a travel mentor for Unfold India. Your goal is to encourage users to explore more of India. Keep responses short (max 2 sentences), professional, and inspiring.`;

        const userPrompt = `
        User Stats:
        - India Explored: ${india_progress}%
        - Top Styles: ${top_travel_styles.join(', ')}
        - Unlocked Badges: ${unlocked_badges.join(', ')}
        - Unexplored Regions: ${unexplored_regions.join(', ')}
        
        Generate a short insight about their progress.`;

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
                max_tokens: 100,
            }),
        });

        const aiData = await response.json();

        if (!response.ok) {
            console.error('Groq API Error:', aiData);
            throw new Error(aiData.error?.message || 'Failed to fetch insight from Groq');
        }

        const aiResponse = aiData.choices[0]?.message?.content || "Keep exploring to unlock more insights!";

        // 4. Save to Cache
        await supabaseClient.from('user_progress_insights').insert({
            user_id: user.id,
            insight_type,
            input_hash: inputHash,
            output_text: aiResponse
        });

        return new Response(JSON.stringify({ insight: aiResponse, cached: false }), {
            headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        });

    } catch (error) {
        return new Response(JSON.stringify({ error: error.message }), {
            status: 400,
            headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        });
    }
});
