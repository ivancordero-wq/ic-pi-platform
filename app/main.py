{% extends "base.html" %}

{% block title %}Rho Gate | IC-Pi{% endblock %}

{% block content %}
<div class="flex min-h-screen bg-slate-900">

    <!-- Sidebar -->
    <aside class="w-64 bg-slate-800 border-r border-slate-700 p-6 flex flex-col">
        <div class="mb-8">
            <h1 class="text-xl font-bold text-cyan-400">IC-Pi</h1>
            <p class="text-xs text-slate-400 mt-1">Licensed Consultant</p>
        </div>
        <nav class="flex-1 space-y-2">
            <a href="/dashboard" class="block px-3 py-2 rounded text-sm text-slate-300 hover:bg-slate-700 hover:text-white transition">
                &#128202; Dashboard
            </a>
            <a href="/project/new" class="block px-3 py-2 rounded text-sm text-slate-300 hover:bg-slate-700 hover:text-white transition">
                &#128193; Projects
            </a>
            <a href="#" class="block px-3 py-2 rounded text-sm text-white bg-slate-700">
                &#128269; Discoveries
            </a>
            <a href="#" class="block px-3 py-2 rounded text-sm text-slate-300 hover:bg-slate-700 hover:text-white transition">
                &#128196; Blueprints
            </a>
            <a href="#" class="block px-3 py-2 rounded text-sm text-slate-300 hover:bg-slate-700 hover:text-white transition">
                &#128200; Performance
            </a>
        </nav>
        <div class="pt-4 border-t border-slate-700">
            <p class="text-xs text-slate-400">Logged in as</p>
            <p class="text-sm text-white">{{ consultant_name }}</p>
            <a href="/logout" class="text-xs text-red-400 hover:text-red-300 mt-1 inline-block">Sign Out</a>
        </div>
    </aside>

    <!-- Main Content -->
    <main class="flex-1 p-8 overflow-y-auto">
        <div class="max-w-5xl mx-auto">

            <!-- Header -->
            <div class="mb-6">
                <p class="text-xs text-slate-400 uppercase tracking-wide mb-1">Screen 3B &middot; Discovery</p>
                <h2 class="text-2xl font-bold text-white">&#961; Gate: Relevance Voting</h2>
                <p class="text-sm text-slate-400 mt-1">{{ process.name }} &mdash; {{ discovery.name }}</p>
            </div>

            <!-- Rules Callout -->
            <div class="bg-slate-800 rounded-lg p-5 mb-6 border border-cyan-500/30">
                <h3 class="text-sm font-semibold text-cyan-400 mb-3">&#961; Gate Rules (Fully Algorithmic, No Human Override)</h3>
                <div class="grid grid-cols-2 gap-3 text-xs text-slate-300">
                    <div class="flex gap-2">
                        <span class="inline-block w-5 h-5 rounded-full bg-green-600 text-center text-white font-bold leading-5 flex-shrink-0">1</span>
                        <span><strong class="text-green-400">Survived:</strong> At least 1 SME voted YES. Even one voice is enough.</span>
                    </div>
                    <div class="flex gap-2">
                        <span class="inline-block w-5 h-5 rounded-full bg-yellow-600 text-center text-white font-bold leading-5 flex-shrink-0">2</span>
                        <span><strong class="text-yellow-400">Unresolved:</strong> 0 YES votes. Re-surfaced next round with aggregates visible.</span>
                    </div>
                    <div class="flex gap-2">
                        <span class="inline-block w-5 h-5 rounded-full bg-slate-600 text-center text-white font-bold leading-5 flex-shrink-0">3</span>
                        <span><strong class="text-slate-300">Max 3 rounds.</strong> After round 3, still 0 YES = automatically removed.</span>
                    </div>
                    <div class="flex gap-2">
                        <span class="inline-block w-5 h-5 rounded-full bg-cyan-600 text-center text-white font-bold leading-5 flex-shrink-0">4</span>
                        <span><strong class="text-cyan-400">Exit:</strong> Gate locks when 0 unresolved remain. Only survived move forward.</span>
                    </div>
                </div>
            </div>

            <!-- Status Bar -->
            <div class="flex items-center gap-6 mb-6 bg-slate-800 rounded-lg p-4 border border-slate-700">
                <!-- Round Indicator -->
                <div class="flex items-center gap-2">
                    <span class="text-xs text-slate-400 uppercase">Round</span>
                    {% for r in range(1, 4) %}
                    <span class="w-3 h-3 rounded-full {% if r <= current_round %}bg-cyan-400{% else %}bg-slate-600{% endif %}"></span>
                    {% endfor %}
                    <span class="text-sm text-white font-semibold ml-1">{{ current_round }}/3</span>
                </div>

                <!-- SME Responses -->
                <div class="flex items-center gap-2">
                    <span class="text-xs text-slate-400 uppercase">SMEs</span>
                    {% for s in range(total_smes) %}
                    <span class="w-3 h-3 rounded-full {% if s < smes_responded %}bg-green-400{% else %}bg-slate-600{% endif %}"></span>
                    {% endfor %}
                    <span class="text-sm text-white ml-1">{{ smes_responded }}/{{ total_smes }}</span>
                </div>

                <!-- Unresolved Count -->
                <div class="flex items-center gap-2">
                    <span class="text-xs text-slate-400 uppercase">Unresolved</span>
                    <span class="text-sm font-semibold {% if unresolved_count > 0 %}text-yellow-400{% else %}text-green-400{% endif %}">{{ unresolved_count }}</span>
                </div>

                <!-- Status Text -->
                <div class="ml-auto">
                    {% if gate_locked %}
                    <span class="px-3 py-1 rounded-full text-xs font-semibold bg-green-600 text-white">LOCKED</span>
                    {% elif unresolved_count == 0 and survived_count > 0 %}
                    <span class="px-3 py-1 rounded-full text-xs font-semibold bg-cyan-600 text-white">Ready to Lock</span>
                    {% else %}
                    <span class="px-3 py-1 rounded-full text-xs font-semibold bg-yellow-600 text-black">Voting Active</span>
                    {% endif %}
                </div>
            </div>

            <!-- Parameter Table -->
            <div class="bg-slate-800 rounded-lg border border-slate-700 mb-6 overflow-hidden">
                <table class="w-full text-sm">
                    <thead>
                        <tr class="border-b border-slate-700 text-slate-400">
                            <th class="text-left py-3 px-4">Parameter</th>
                            <th class="text-left py-3 px-4 w-24">Source</th>
                            <th class="text-left py-3 px-4 w-48">Votes</th>
                            <th class="text-center py-3 px-4 w-20">Y / U / N</th>
                            <th class="text-center py-3 px-4 w-28">Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for param in parameters %}
                        <tr class="border-b border-slate-700/50 {{ param.row_class }}">
                            <!-- Name + Description -->
                            <td class="py-3 px-4">
                                <p class="text-white font-medium">{{ param.name }}</p>
                                {% if param.description %}
                                <p class="text-xs text-slate-400 mt-0.5">{{ param.description }}</p>
                                {% endif %}
                                {% if param.status == "unresolved" %}
                                <p class="text-xs text-yellow-400 italic mt-1">0 YES votes. Will re-surface in Round {{ param.next_round }}.</p>
                                {% endif %}
                            </td>

                            <!-- Source Badge -->
                            <td class="py-3 px-4">
                                {% if param.source == "standard" %}
                                <span class="px-2 py-0.5 rounded text-xs bg-slate-600 text-slate-300">Standard</span>
                                {% elif param.source == "regulation" %}
                                <span class="px-2 py-0.5 rounded text-xs bg-purple-600/50 text-purple-300">Regulation</span>
                                {% else %}
                                <span class="px-2 py-0.5 rounded text-xs bg-cyan-600/50 text-cyan-300">AI-identified</span>
                                {% endif %}
                            </td>

                            <!-- Vote Bar -->
                            <td class="py-3 px-4">
                                {% set total = param.yes + param.no + param.unsure %}
                                {% if total > 0 %}
                                <div class="flex h-4 rounded overflow-hidden bg-slate-700">
                                    {% if param.yes > 0 %}
                                    <div class="bg-green-500 h-full" style="width: {{ (param.yes / total * 100)|int }}%"></div>
                                    {% endif %}
                                    {% if param.unsure > 0 %}
                                    <div class="bg-yellow-500 h-full" style="width: {{ (param.unsure / total * 100)|int }}%"></div>
                                    {% endif %}
                                    {% if param.no > 0 %}
                                    <div class="bg-red-500 h-full" style="width: {{ (param.no / total * 100)|int }}%"></div>
                                    {% endif %}
                                </div>
                                {% else %}
                                <div class="h-4 rounded bg-slate-700 flex items-center justify-center">
                                    <span class="text-xs text-slate-500">Awaiting votes</span>
                                </div>
                                {% endif %}
                            </td>

                            <!-- Vote Counts -->
                            <td class="py-3 px-4 text-center">
                                <span class="text-green-400">{{ param.yes }}</span>
                                <span class="text-slate-500">/</span>
                                <span class="text-yellow-400">{{ param.unsure }}</span>
                                <span class="text-slate-500">/</span>
                                <span class="text-red-400">{{ param.no }}</span>
                            </td>

                            <!-- Status Badge -->
                            <td class="py-3 px-4 text-center">
                                <span class="px-3 py-1 rounded-full text-xs font-semibold text-white {{ param.badge_class }}">
                                    {{ param.status|capitalize }}
                                </span>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>

            <!-- Summary Block -->
            <div class="grid grid-cols-3 gap-4 mb-8">
                <div class="bg-green-900/20 border border-green-500/30 rounded-lg p-4 text-center">
                    <p class="text-3xl font-bold text-green-400">{{ survived_count }}</p>
                    <p class="text-xs text-green-300 mt-1 uppercase">Survived</p>
                    <p class="text-xs text-slate-400 mt-0.5">At least 1 YES</p>
                </div>
                <div class="bg-yellow-900/20 border border-yellow-500/30 rounded-lg p-4 text-center">
                    <p class="text-3xl font-bold text-yellow-400">{{ unresolved_count }}</p>
                    <p class="text-xs text-yellow-300 mt-1 uppercase">Unresolved</p>
                    <p class="text-xs text-slate-400 mt-0.5">0 YES (pending)</p>
                </div>
                <div class="bg-slate-700/30 border border-slate-600 rounded-lg p-4 text-center">
                    <p class="text-3xl font-bold text-slate-400">{{ removed_count }}</p>
                    <p class="text-xs text-slate-300 mt-1 uppercase">Removed</p>
                    <p class="text-xs text-slate-400 mt-0.5">0 YES after 3 rounds</p>
                </div>
            </div>

            <!-- CTAs -->
            {% if not gate_locked %}
            <div class="flex items-center gap-4">
                {% if can_lock %}
                <form action="/discovery/{{ discovery.id }}/rho-gate/lock" method="POST">
                    <button type="submit" class="px-6 py-3 rounded bg-green-600 hover:bg-green-500 text-white font-semibold transition">
                        Lock &#961; Gate & Proceed to Weighting
                    </button>
                </form>
                {% endif %}

                {% if can_trigger_next %}
                <form action="/discovery/{{ discovery.id }}/rho-gate/trigger-round" method="POST">
                    <button type="submit" class="px-6 py-3 rounded bg-yellow-600 hover:bg-yellow-500 text-black font-semibold transition">
                        Trigger Round {{ current_round + 1 }} ({{ unresolved_count }} unresolved)
                    </button>
                </form>
                {% endif %}

                <a href="/dashboard" class="text-sm text-slate-400 hover:text-white ml-2">Back to Dashboard</a>
            </div>
            {% else %}
            <div class="p-4 rounded-lg bg-green-900/20 border border-green-500/30">
                <p class="text-green-300 font-semibold">&#961; Gate is locked. {{ survived_count }} parameters proceed to weighting (Screen 3C).</p>
                <a href="/dashboard" class="text-sm text-cyan-400 hover:text-cyan-300 mt-2 inline-block">Back to Dashboard</a>
            </div>
            {% endif %}

        </div>
    </main>
</div>
{% endblock %}
