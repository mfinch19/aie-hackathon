import os
import json
import asyncio
from datetime import datetime
from typing import TypedDict, Annotated, List, Dict, Any
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Browser, Page
from langgraph.graph import StateGraph, START, END
from langchain_google_genai import ChatGoogleGenerativeAI
import builtins
import functools
import sys


load_dotenv()
sys.stdout.reconfigure(line_buffering=True)

print = functools.partial(builtins.print, flush=True)

# --- 1. STATE DEFINITION (RL INFRASTRUCTURE) ---
class AgentState(TypedDict):
    browser: Browser
    page: Page
    url: str
    steps: int
    maxSteps: int
    logs: Annotated[List[str], lambda x, y: x + y]
    issues: Annotated[List[str], lambda x, y: x + y]
    screenshotRefs: Annotated[List[str], lambda x, y: x + y]
    visitedUrls: Annotated[List[str], lambda x, y: x + y]
    lastAction: str
    actionPayload: dict
    # RL SPECIFIC FIELDS
    cumulativeReward: float
    stepRewards: Annotated[List[float], lambda x, y: x + y]
    trajectory: Annotated[List[Dict[str, Any]], lambda x, y: x + y]

# Helper to sanitize filenames
def sanitize(s: str) -> str:
    return ''.join(c if c.isalnum() else '_' for c in s).lower()

# --- 2. NODES ---

async def initialize_browser(state: AgentState) -> dict:
    print("🚀 Initializing Security Gym Environment...")

    if not os.path.exists("qa_screenshots"):
        os.makedirs("qa_screenshots")

    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=False)
    page = await browser.new_page()
    
    # CHANGE THIS TO YOUR TARGET URL
    target_url = "https://strandschat.com" 
    try:
        await page.goto(target_url)
    except Exception as e:
        print(f"Warning: Could not load {target_url}. Make sure server is running.")

    return {
        "browser": browser,
        "page": page,
        "url": target_url,
        "steps": 0,
        "maxSteps": 20, # Increased steps to allow for exploration
        "logs": ["Started RL Training Session."],
        "visitedUrls": [target_url],
        # Initialize RL State
        "cumulativeReward": 0.0,
        "stepRewards": [],
        "trajectory": []
    }

async def analyze_and_decide(state: AgentState) -> dict:
    page = state["page"]
    steps = state["steps"]
    maxSteps = state["maxSteps"]
    logs = state["logs"]
    current_reward = state.get("cumulativeReward", 0.0)

    if steps >= maxSteps:
        return {"lastAction": "finish"}

    # 1. Get Observation (Interactive Elements)
    buttons = await page.query_selector_all('button, input, a[href], [role="button"], textarea, select')
    visible_elements = []
    
    for i, el in enumerate(buttons):
        try:
            if await el.is_visible() and await el.is_enabled():
                tag = await el.evaluate("e => e.tagName.toLowerCase()")
                eid = await el.get_attribute('id') or f"el-{i}"
                text = await el.inner_text()
                placeholder = await el.get_attribute("placeholder")
                info = text[:20] if text else (placeholder if placeholder else "")
                
                visible_elements.append(f"- Index {i}: <{tag} id='{eid}'> {info}")
        except:
            continue

    element_list = "\n".join(visible_elements[:50]) # Limit context size

    # 2. Check History for Warnings (The "Memory" logic)
    trajectory = state.get("trajectory", [])
    last_move_warning = ""
    if len(trajectory) > 0:
        last_move = trajectory[-1]
        if last_move['reward'] < 0:
            last_move_warning = f"⚠️ WARNING: Your last action '{last_move['action']}' received a NEGATIVE reward ({last_move['reward']}). DO NOT REPEAT IT."
        else:
            last_move_warning = f"NOTE: You just did '{last_move['action']}'. Try a DIFFERENT action to find new vulnerabilities."

    print(f"🤔 Agent Thinking... (Current Reward: {current_reward})")
    
    # Add delay to make the loop observable
    await asyncio.sleep(2)  # 2 second delay between iterations

    # 3. The Policy Model (Gemini)
    model = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash-exp", # Or gemini-1.5-pro
        api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0.1,
    )

    prompt = f"""
    You are an RL Agent training to find security vulnerabilities and robustness issues.
    
    Current State:
    - URL: {page.url}
    - Steps Taken: {steps}/{maxSteps}
    - Cumulative Reward: {current_reward} (Maximize this!)
    
    {last_move_warning} <--- CRITICAL INSTRUCTION
    
    Interactive Elements:
    {element_list}
    
    Recent Logs:
    {chr(10).join(logs[-3:])}
    
    YOUR GOAL: Maximize your Reward Score.
    - +1.0: Cause Server Error (500), Crash, SQLi success, XSS Alert.
    - +0.1: Valid, NEW interaction (200 OK).
    - -0.5: STAGNATION (Repeating the same action).
    - -1.0: Failed action (Element not found).
    
    Choose your next action. EXPLAIN YOUR THINKING - this will be shown in the UI!
    
    Return ONLY JSON with this structure:
    {{
      "thinking": "What you see + why you're doing this (1-2 sentences)",
      "action": "fill_input" | "click_element" | "check_responsiveness" | "finish",
      "targetIndex": <number>,
      "inputValue": "<test_payload>",
      "expecting": "What should happen if this works"
    }}
    
    Example:
    {{
      "thinking": "I see a login form with email/password fields. The email input might be vulnerable to SQLi, so I'll try a basic authentication bypass payload.",
      "action": "fill_input",
      "targetIndex": 3,
      "inputValue": "' OR 1=1--",
      "expecting": "If vulnerable, I should bypass authentication or see a SQL error message"
    }}
    
    (Example payloads: "test<script>alert(1)</script>", "' OR '1'='1", "admin")
    """

    try:
        response = await model.ainvoke(prompt)
        content = str(response.content).replace("```json", "").replace("```", "").strip()
        
        # Extract JSON
        if "{" in content:
            content = content[content.find("{"):content.rfind("}")+1]
            
        decision = json.loads(content)
        
        # Print the agent's thinking for UI/debugging
        print(f"\n💭 THINKING: {decision.get('thinking', 'N/A')}")
        print(f"⚡ ACTION: {decision['action']}")
        if decision.get('inputValue'):
            print(f"💉 PAYLOAD: {decision.get('inputValue')}")
        print(f"🔮 EXPECTING: {decision.get('expecting', 'N/A')}\n")
        
        return {
            "lastAction": decision["action"],
            "actionPayload": {
                "targetIndex": decision.get("targetIndex"),
                "thinking": decision.get("thinking", ""),
                "expecting": decision.get("expecting", ""),
                "inputValue": decision.get("inputValue", "")
            }
        }
    except Exception as e:
        print(f"Fallback: {e}")
        return {"lastAction": "finish"}

async def execute_action(state: AgentState) -> dict:
    page = state["page"]
    action = state["lastAction"]
    payload = state.get("actionPayload", {})
    steps = state["steps"]
    logs = []
    screenshot_refs = []
    
    # NEW: Track details about the specific element we touched for the Exploiter Script
    target_element_details = {} 

    try:
        elements = await page.query_selector_all('button, input, a[href], [role="button"], textarea, select')
        idx = payload.get("targetIndex")
        
        # Validate Index and Capture Identity
        target_el = None
        if idx is not None and idx < len(elements):
            target_el = elements[idx]
            
            # --- CAPTURE ELEMENT IDENTITY ---
            try:
                target_element_details = {
                    "tagName": await target_el.evaluate("e => e.tagName.toLowerCase()"),
                    "id": await target_el.get_attribute("id") or "no-id",
                    "name": await target_el.get_attribute("name") or "no-name",
                    "placeholder": await target_el.get_attribute("placeholder") or "",
                    "outerHTML": await target_el.evaluate("e => e.outerHTML.substring(0, 150)") # First 150 chars
                }
            except:
                target_element_details = {"error": "could_not_capture_details"}
            # -------------------------------

        if action == "fill_input" and target_el:
            val = payload.get("inputValue", "test")
            await target_el.fill(val)
            logs.append(f"Action: Filled input index {idx} ({target_element_details.get('id')}) with '{val}'")
                
        elif action == "click_element" and target_el:
            await target_el.click()
            logs.append(f"Action: Clicked element index {idx} ({target_element_details.get('id')})")
            await page.wait_for_timeout(1000) # Wait for reaction

        elif action == "check_responsiveness":
            logs.append("Action: Checked Responsiveness")
            await page.set_viewport_size({"width": 375, "height": 667})
            await page.wait_for_timeout(500)
            await page.set_viewport_size({"width": 1280, "height": 800})

        # Capture State (Screenshot)
        path = f"qa_screenshots/step_{steps}.png"
        await page.screenshot(path=path)
        screenshot_refs.append(path)

    except Exception as e:
        logs.append(f"Error: {str(e)}")
    
    # Pass these details to the next node (Reward Node)
    return {
        "steps": steps + 1,
        "logs": logs,
        "screenshotRefs": screenshot_refs,
        # UPDATE PAYLOAD with target details so Reward Node can see them
        "actionPayload": {**payload, "targetDetails": target_element_details} 
    }

# --- 3. THE REWARD MODEL NODE (Evidence-Based, No Hallucination) ---
async def evaluate_reward(state: AgentState) -> dict:
    """
    Calculates the scalar reward for the last action. 
    Checks ACTUAL page state instead of hallucinating from logs.
    """
    page = state["page"]
    logs = state["logs"][-1]
    last_action = state["lastAction"]
    step = state["steps"]
    
    # Retrieve the target details captured in execute_action
    last_payload = state.get("actionPayload", {})
    target_details = last_payload.get("targetDetails", {})
    
    # 1. Check for Repetition
    trajectory = state.get("trajectory", [])
    is_repeat = False
    if len(trajectory) > 0:
        prev = trajectory[-1]
        if prev["action"] == last_action and "finish" not in last_action:
            is_repeat = True

    # 2. ACTUAL EVIDENCE CHECKS (Not hallucination)
    score = 0.0
    reason = "No significant outcome"
    
    try:
        # Check page title for error indicators
        title = await page.title()
        url = page.url
        
        # REAL CHECKS:
        if "500" in title or "Internal Server Error" in title:
            score = 1.0
            reason = "🔥 Server Error (500) detected - REAL vulnerability found!"
        elif "error" in title.lower() and "404" not in title:
            score = 0.8
            reason = "⚠️ Error page detected - potential vulnerability"
        elif "404" in title:
            score = 0.5
            reason = "404 Not Found - Robustness issue"
        elif is_repeat:
            score = -0.5
            reason = "Stagnation: Repeated action"
        elif "Error" in logs or "failed" in logs.lower():
            score = -1.0
            reason = "Action execution failed"
        elif last_action == "fill_input":
            # For inputs, give small reward for trying, but don't hallucinate success
            score = 0.1
            reason = "Input filled successfully (no crash detected)"
        elif last_action == "click_element":
            score = 0.1
            reason = "Click executed successfully"
        else:
            score = 0.1
            reason = "Standard action completed"
            
    except Exception as e:
        score = -1.0
        reason = f"Error during evaluation: {str(e)}"

    print(f"💰 REWARD: {score} ({reason})")
    
    # Save Experience Tuple (S, A, R) AND THE TARGET IDENTITY
    experience = {
        "step": step,
        "action": last_action,
        "target": target_details,  # <--- SAVED FOR EXPLOITER SCRIPT
        "log": logs,
        "reward": score,
        "reason": reason
    }
    
    return {
        "cumulativeReward": state.get("cumulativeReward", 0) + score,
        "stepRewards": state.get("stepRewards", []) + [score],
        "trajectory": state.get("trajectory", []) + [experience]
    }

async def generate_report(state: AgentState) -> dict:
    print("📝 Generating Training Artifacts...")
    
    # 1. Save the RL Dataset (The "Post-Training" Artifact)
    with open("rl_training_data.json", "w") as f:
        json.dump(state["trajectory"], f, indent=2)
        print("✅ Saved rl_training_data.json (Dataset)")

    # 2. Generate Human Report
    reward_chart = "\n".join([f"- Step {i}: **{r}**" for i, r in enumerate(state["stepRewards"])])
    
    report = f"""# Security Gym Training Report
**Date**: {datetime.now()}
**Total Steps**: {state['steps']}
**Cumulative Reward**: {state['cumulativeReward']}

## 📈 Reward Signal (RL Feedback)
The following reward signal was generated by the Automated Reward Model:
{reward_chart}

## 🤖 Execution Log
{chr(10).join([f"- {l}" for l in state['logs']])}

## 📸 Visual State
![Final State]({state['screenshotRefs'][-1] if state['screenshotRefs'] else ''})

*Generated by SecGym Environment*
"""
    with open("qa_report.md", "w") as f:
        f.write(report)
    
    if state.get("browser"):
        await state["browser"].close()
        
    return {"logs": ["Training Complete."]}

# --- 4. GRAPH CONSTRUCTION ---
def should_continue(state: AgentState) -> str:
    if state.get("lastAction") == "finish":
        return "generateReport"
    return "executeAction"

def create_workflow():
    workflow = StateGraph(AgentState)

    workflow.add_node("initialize", initialize_browser)
    workflow.add_node("analyze", analyze_and_decide)
    workflow.add_node("executeAction", execute_action)
    workflow.add_node("evaluateReward", evaluate_reward) # <--- REWARD NODE
    workflow.add_node("generateReport", generate_report)

    workflow.add_edge(START, "initialize")
    workflow.add_edge("initialize", "analyze")
    
    # THE LOOP: Analyze -> Execute -> Reward -> Analyze
    workflow.add_conditional_edges(
        "analyze",
        should_continue,
        {
            "executeAction": "executeAction",
            "generateReport": "generateReport"
        }
    )
    workflow.add_edge("executeAction", "evaluateReward")
    workflow.add_edge("evaluateReward", "analyze")
    
    workflow.add_edge("generateReport", END)

    return workflow.compile()

async def main():
    print("🏎️ Starting SecGym Agent...")
    app = create_workflow()
    await app.ainvoke({}, config={"recursion_limit": 1000})
    print("✅ Session Finished. Check 'rl_training_data.json' and 'qa_report.md'.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())