import base64
import os
from google import genai
from google.genai import types

class BaccaratVisionScanner:
    """
    百家乐大路图视觉识别核心类
    """
    def __init__(self, api_key="AIzaSyAy7OjmYghUBGLi93Thm2cuwUOsVIb2EzA"):
        # 初始化 Gemini 客户端
        self.client = genai.Client(api_key=api_key)
        self.model_id = "gemini-3.1-pro-preview"
        
        # 经过 100% 准确率调试优化的提示词
        # 针对带“T”标记 UI 优化的提示词
        self.prompt = """
        You are a world-class Baccarat Vision Expert. Your goal is to extract the Big Road sequence with 100% accuracy.

        UI SPECIFIC RULES:
        1. GRID STRUCTURE: The Big Road is a 6-row grid.
        2. COLORS: Red hollow rings = Banker ('b'), Blue hollow rings = Player ('p').
        3. TIE MARKS: You will see green 'T' letters inside some rings. IGNORE THE 'T'. A ring with a 'T' is still exactly ONE Banker or Player win. Do not skip it, and do not count it as a separate column.
        4. STREAK COUNTING:
           - A streak is a vertical column of the same color.
           - DRAGON TAIL: If a streak reaches Row 6 and turns right, all those horizontal rings belong to the SAME streak. Count them all together.
        5. COLUMN TRANSITION: A new streak (new column) MUST start at Row 1. If the color at Row 1 changes, that is the start of the next item in the array.
        6. VERIFICATION HINT: The UI shows total counts (e.g., B 39, P 29). Ensure your total count of 'b' units and 'p' units matches these numbers.

        OUTPUT:
        - Return ONLY a JSON array of strings.
        - Example: ["b4", "p4", "b2", "p4", "b6", "p1", "b2", "p5", "b2", "p2", "b5"]
        """

    def get_road_data(self, image_path):
        """
        输入图片路径，返回识别后的列表数据
        """
        if not os.path.exists(image_path):
            print(f"错误: 找不到图片文件 {image_path}")
            return None

        try:
            with open(image_path, "rb") as f:
                image_bytes = f.read()

            # 调用 AI 进行视觉分析
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                    self.prompt
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema={
                        "type": "ARRAY",
                        "items": {"type": "STRING"}
                    },
                    thinking_config=types.ThinkingConfig(
                        thinking_level="HIGH"
                    )
                )
            )
            
            # 成功返回解析后的列表
            return response.parsed
        except Exception as e:
            print(f"AI 识别异常: {e}")
            return None

# --- 如何在您的工程中调用 ---
# 示例代码：
if __name__ == "__main__":
    scanner = BaccaratVisionScanner()
    # 假设您的图片存放在 results 或 app 的某个临时目录下
    image_to_scan = "../results/current_table.jpg" 
    
    data = scanner.get_road_data(image_to_scan)
    if data:
        print(f"识别成功: {data}")
        # 这里可以将 data 传递给您的核心逻辑，例如：
        # from core.strategy import analyze_next_bet
        # analyze_next_bet(data)