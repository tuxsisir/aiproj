from django.shortcuts import render
from django.http import HttpResponse


def landing_page(request):
    return render(request, "landing.html")


def dashboard_demo(request):
    return render(request, "dashboard_demo.html")


def documents(request):
    return render(request, "documents.html")


def queries(request):
    return render(request, "queries.html")


def chat_response(request):
    # This responds to the HTMX request
    if request.method == "POST":
        query = request.POST.get("query", "")
        # HTML response simulating the AI citation extraction
        response_html = f"""
        <div class="flex flex-col space-y-2 htmx-added mb-4">
            <div class="self-end bg-blue-600 text-white rounded-lg py-2.5 px-4 max-w-[80%] text-sm shadow-sm">
                {query}
            </div>
            <div class="self-start bg-zinc-800 text-zinc-100 rounded-lg py-3 px-5 max-w-[85%] border border-zinc-700/50 shadow-sm leading-relaxed text-sm mt-3">
                <span class="text-emerald-400 font-semibold mb-1.5 flex items-center gap-1.5">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"></rect><circle cx="12" cy="5" r="2"></circle><path d="M12 7v4"></path></svg>
                    Assistant
                </span>
                <p>(Source: Bylaw Section 14.2, page 11) - Kayaks must be stored inside designated storage lockers only.</p>
            </div>
        </div>
        """
        return HttpResponse(response_html)
    return HttpResponse("")
