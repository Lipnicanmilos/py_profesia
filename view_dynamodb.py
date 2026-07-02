import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError
import json

def view_all_items(table_name='JobsTable_Profesia', limit=50):
    """Zobrazí všetky položky z DynamoDB tabuľky."""
    try:
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(table_name)
        
        print(f"📊 Načítavám dáta z tabuľky '{table_name}'...\n")
        
        resp = table.scan(Limit=limit)
        items = resp.get('Items', [])
        
        if not items:
            print("❌ Tabuľka je prázdna alebo sa nenašli položky.")
            return
        
        print(f"✅ Nájdených {len(items)} položiek:\n")
        print("=" * 100)
        
        for i, item in enumerate(items, 1):
            print(f"\n{i}. POZÍCIA: {item.get('title', 'N/A')}")
            print(f"   Zamestnávateľ: {item.get('employer', 'N/A')}")
            print(f"   Plat: {item.get('salary', 'N/A')}")
            print(f"   Miesto: {item.get('location', 'N/A')}")
            print(f"   Dátum: {item.get('date', 'N/A')}")
            print(f"   Parsovaný dátum: {item.get('parsed_date', 'N/A')}")
            print(f"   Oslovená: {'Áno' if item.get('contacted', 0) == 1 else 'Nie'}")
            print(f"   Link: {item.get('link', 'N/A')[:80]}...")
            if item.get('answer_info'):
                print(f"   Poznámka: {item.get('answer_info', '')}")
            print("-" * 100)
        
        if resp.get('LastEvaluatedKey'):
            print(f"\n⚠️ Je ich viac ako {limit}. Spustite znova s väčšim limitom.")
    
    except ClientError as e:
        print(f"❌ AWS chyba: {e.response['Error']['Message']}")
    except Exception as e:
        print(f"❌ Chyba: {e}")


def view_uncontacted(table_name='JobsTable_Profesia', limit=50):
    """Zobrazí iba neoslovené ponuky."""
    try:
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(table_name)
        
        print(f"📊 Neoslovené ponuky z '{table_name}'...\n")
        
        resp = table.scan(
            FilterExpression=Attr('contacted').eq(0),
            Limit=limit
        )
        items = resp.get('Items', [])
        
        if not items:
            print("✅ Všetky ponuky sú oslovené!")
            return
        
        print(f"❌ Celkovo {len(items)} neoslovených pozícií:\n")
        print("=" * 100)
        
        for i, item in enumerate(items, 1):
            print(f"\n{i}. {item.get('title', 'N/A')} | {item.get('employer', 'N/A')}")
            print(f"   Plat: {item.get('salary', 'N/A')} | Dátum: {item.get('date', 'N/A')}")
            print(f"   Link: {item.get('link', 'N/A')}")
            print("-" * 100)
    
    except ClientError as e:
        print(f"❌ AWS chyba: {e.response['Error']['Message']}")
    except Exception as e:
        print(f"❌ Chyba: {e}")


def export_to_json(table_name='JobsTable_Profesia', filename='export.json'):
    """Exportuje všetky položky do JSON súboru."""
    try:
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(table_name)
        
        print(f"📤 Exportujem dáta do '{filename}'...\n")
        
        resp = table.scan()
        items = resp.get('Items', [])
        
        # Konvertuj DynamoDB format na JSON
        for item in items:
            # DynamoDB Decimal na float
            item['contacted'] = int(item.get('contacted', 0))
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        
        print(f"✅ Exportované {len(items)} položiek do '{filename}'")
    
    except ClientError as e:
        print(f"❌ AWS chyba: {e.response['Error']['Message']}")
    except Exception as e:
        print(f"❌ Chyba: {e}")


def search_by_keyword(keyword, table_name='JobsTable_Profesia'):
    """Vyhľadá položky podľa kľúčového slova v názve alebo firme."""
    try:
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(table_name)
        
        keyword_lower = keyword.lower()
        print(f"🔍 Hľadám '{keyword}'...\n")
        
        resp = table.scan()
        items = resp.get('Items', [])
        
        results = [
            item for item in items 
            if keyword_lower in item.get('title', '').lower() 
            or keyword_lower in item.get('employer', '').lower()
        ]
        
        if not results:
            print(f"❌ Nič sa nenašlo pre '{keyword}'")
            return
        
        print(f"✅ Nájdených {len(results)} výsledkov:\n")
        
        for i, item in enumerate(results, 1):
            print(f"{i}. {item.get('title', 'N/A')} | {item.get('employer', 'N/A')}")
            print(f"   Plat: {item.get('salary', 'N/A')} | Link: {item.get('link', 'N/A')[:60]}...")
            print()
    
    except ClientError as e:
        print(f"❌ AWS chyba: {e.response['Error']['Message']}")
    except Exception as e:
        print(f"❌ Chyba: {e}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        
        if cmd == 'all':
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else 50
            view_all_items(limit=limit)
        
        elif cmd == 'uncontacted':
            view_uncontacted()
        
        elif cmd == 'export':
            filename = sys.argv[2] if len(sys.argv) > 2 else 'jobs_export.json'
            export_to_json(filename=filename)
        
        elif cmd == 'search':
            if len(sys.argv) > 2:
                search_by_keyword(sys.argv[2])
            else:
                print("❌ Zadaj kľúčové slovo: python view_dynamodb.py search 'python'")
        
        else:
            print("❓ Neznámy príkaz")
    else:
        print("📖 Použitie:")
        print("  python view_dynamodb.py all [limit]          - Všetky položky")
        print("  python view_dynamodb.py uncontacted          - Iba neoslovené")
        print("  python view_dynamodb.py export [filename]    - Export do JSON")
        print("  python view_dynamodb.py search 'keyword'     - Hľadať")
        print("\nPríklad:")
        print("  python view_dynamodb.py all 100")
        print("  python view_dynamodb.py search 'python'")
