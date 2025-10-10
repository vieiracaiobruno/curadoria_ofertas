#!/usr/bin/env python3
"""
Test script for the new link collection and parsing flow.
Tests without actual Selenium (mocked data).
"""
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from backend.db.database import SessionLocal
from backend.models.models import LinkColeta
from backend.modules.services.link_collector_service import LinkCollectorService


def test_link_collection():
    """Test saving links to the database."""
    print("=" * 60)
    print("Test 1: Link Collection Service")
    print("=" * 60)
    
    db = SessionLocal()
    
    try:
        # Sample links (simulating collector output)
        sample_links = [
            {"url_base": "https://mercadolivre.com.br/produto1", "source": "mercadolivre"},
            {"url_base": "https://mercadolivre.com.br/produto2", "source": "mercadolivre"},
            {"url_base": "https://mercadolivre.com.br/produto3", "source": "mercadolivre"},
            {"url_base": "https://mercadolivre.com.br/produto1", "source": "mercadolivre"},  # Duplicate
        ]
        
        # Save links
        service = LinkCollectorService(db)
        stats = service.save_links(sample_links)
        
        print(f"\n✓ Links processed: {stats['total_received']}")
        print(f"  - Inserted: {stats['inserted']}")
        print(f"  - Duplicates: {stats['duplicates']}")
        print(f"  - Errors: {stats['errors']}")
        
        # Verify in database
        count = db.query(LinkColeta).filter(LinkColeta.ativo == True).count()
        print(f"\n✓ Active links in database: {count}")
        
        # Show sample records
        links = db.query(LinkColeta).limit(3).all()
        print(f"\n✓ Sample records:")
        for link in links:
            print(f"  - ID: {link.id}, URL: {link.url[:50]}..., Source: {link.source}, Active: {link.ativo}")
        
        print("\n✓ Test 1 PASSED\n")
        return True
        
    except Exception as e:
        print(f"\n✗ Test 1 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def test_duplicate_prevention():
    """Test that duplicate links are not inserted."""
    print("=" * 60)
    print("Test 2: Duplicate Prevention")
    print("=" * 60)
    
    db = SessionLocal()
    
    try:
        # Try to insert the same link twice
        sample_links = [
            {"url_base": "https://mercadolivre.com.br/test-duplicate", "source": "mercadolivre"},
        ]
        
        service = LinkCollectorService(db)
        
        # First insertion
        stats1 = service.save_links(sample_links)
        print(f"\n✓ First insertion: {stats1['inserted']} inserted")
        
        # Second insertion (should be duplicate)
        service2 = LinkCollectorService(db)
        stats2 = service2.save_links(sample_links)
        print(f"✓ Second insertion: {stats2['duplicates']} duplicates")
        
        if stats1['inserted'] == 1 and stats2['duplicates'] == 1:
            print("\n✓ Test 2 PASSED\n")
            return True
        else:
            print("\n✗ Test 2 FAILED: Expected 1 insert and 1 duplicate")
            return False
            
    except Exception as e:
        print(f"\n✗ Test 2 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def test_ttl_cleanup():
    """Test TTL cleanup of expired links."""
    print("=" * 60)
    print("Test 3: TTL Cleanup")
    print("=" * 60)
    
    db = SessionLocal()
    
    try:
        # Create an old link (simulating expired link)
        old_link = LinkColeta(
            url="https://mercadolivre.com.br/expired-link",
            source="mercadolivre",
            ativo=True,
            criado_em=datetime.now() - timedelta(days=2),  # 2 days old
            tentativas=0
        )
        db.add(old_link)
        db.commit()
        print(f"\n✓ Created test link with creation date 2 days ago")
        
        # Count active links before cleanup
        before = db.query(LinkColeta).filter(LinkColeta.ativo == True).count()
        print(f"✓ Active links before cleanup: {before}")
        
        # Run cleanup (TTL = 1 day)
        from backend.modules.services.link_parser import LinkParser
        parser = LinkParser(db)
        parser.cleanup_expired_links()
        
        # Count active links after cleanup
        after = db.query(LinkColeta).filter(LinkColeta.ativo == True).count()
        print(f"✓ Active links after cleanup: {after}")
        
        if after < before:
            print(f"\n✓ Test 3 PASSED (removed {before - after} expired links)\n")
            return True
        else:
            print("\n✗ Test 3 FAILED: No links were removed")
            return False
            
    except Exception as e:
        print(f"\n✗ Test 3 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def test_mark_processed():
    """Test marking links as processed."""
    print("=" * 60)
    print("Test 4: Mark Link as Processed")
    print("=" * 60)
    
    db = SessionLocal()
    
    try:
        # Create a test link
        test_link = LinkColeta(
            url="https://mercadolivre.com.br/test-mark-processed",
            source="mercadolivre",
            ativo=True,
            tentativas=0
        )
        db.add(test_link)
        db.commit()
        link_id = test_link.id
        print(f"\n✓ Created test link ID: {link_id}")
        
        # Mark as processed (success)
        from backend.modules.services.link_parser import LinkParser
        parser = LinkParser(db)
        parser.mark_link_processed(link_id, success=True)
        
        # Verify
        db.expire_all()  # Clear cache
        link = db.query(LinkColeta).filter(LinkColeta.id == link_id).first()
        
        if not link.ativo and link.processado_em is not None:
            print(f"✓ Link marked as inactive: ativo={link.ativo}")
            print(f"✓ Processed timestamp set: {link.processado_em}")
            print("\n✓ Test 4 PASSED\n")
            return True
        else:
            print(f"\n✗ Test 4 FAILED: Link not properly marked (ativo={link.ativo}, processado_em={link.processado_em})")
            return False
            
    except Exception as e:
        print(f"\n✗ Test 4 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def test_mark_failed():
    """Test marking links as failed (increments tentativas)."""
    print("=" * 60)
    print("Test 5: Mark Link as Failed (increment attempts)")
    print("=" * 60)
    
    db = SessionLocal()
    
    try:
        # Create a test link
        test_link = LinkColeta(
            url="https://mercadolivre.com.br/test-mark-failed",
            source="mercadolivre",
            ativo=True,
            tentativas=0
        )
        db.add(test_link)
        db.commit()
        link_id = test_link.id
        print(f"\n✓ Created test link ID: {link_id}")
        
        # Mark as failed (increment tentativas)
        from backend.modules.services.link_parser import LinkParser
        parser = LinkParser(db)
        parser.mark_link_processed(link_id, success=False)
        
        # Verify
        db.expire_all()  # Clear cache
        link = db.query(LinkColeta).filter(LinkColeta.id == link_id).first()
        
        if link.ativo and link.tentativas == 1:
            print(f"✓ Link still active: ativo={link.ativo}")
            print(f"✓ Attempts incremented: tentativas={link.tentativas}")
            print("\n✓ Test 5 PASSED\n")
            return True
        else:
            print(f"\n✗ Test 5 FAILED: Link not properly handled (ativo={link.ativo}, tentativas={link.tentativas})")
            return False
            
    except Exception as e:
        print(f"\n✗ Test 5 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def main():
    print("\n" + "=" * 60)
    print("TESTING LINK COLLECTION AND PARSING INFRASTRUCTURE")
    print("=" * 60 + "\n")
    
    results = []
    
    results.append(("Link Collection Service", test_link_collection()))
    results.append(("Duplicate Prevention", test_duplicate_prevention()))
    results.append(("TTL Cleanup", test_ttl_cleanup()))
    results.append(("Mark Processed", test_mark_processed()))
    results.append(("Mark Failed", test_mark_failed()))
    
    # Summary
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    print("=" * 60 + "\n")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
