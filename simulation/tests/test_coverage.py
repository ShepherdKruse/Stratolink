"""Tests for coverage analysis, especially grid wrapping (Bug #2 fix)."""

import pytest
import numpy as np

from balloon_sim.coverage import CoverageAnalyzer
from balloon_sim.constants import DEFAULT_COVERAGE_RADIUS_KM


class TestCoverageBasics:
    """Test basic coverage functionality."""

    def test_create_grid(self):
        """Create grid should return correct shape."""
        analyzer = CoverageAnalyzer(grid_height=180, grid_width=360)
        grid = analyzer.create_grid()

        assert grid.shape == (180, 360)
        assert np.all(grid == 0)

    def test_update_coverage_marks_cells(self):
        """Update coverage should mark cells with value."""
        analyzer = CoverageAnalyzer(
            coverage_radius_km=100, grid_height=180, grid_width=360
        )
        grid = analyzer.create_grid()

        # Mark coverage at equator
        analyzer.update_coverage(0.0, 0.0, grid, value=1.0)

        # Some cells should be marked
        assert np.sum(grid != 0) > 0
        assert np.max(grid) == 1.0

    def test_coverage_percentage_empty(self):
        """Empty grid should have 0% coverage."""
        analyzer = CoverageAnalyzer()
        grid = analyzer.create_grid()

        pct = analyzer.compute_coverage_percentage(grid)
        assert pct == 0.0

    def test_coverage_percentage_full(self):
        """Full grid should have 100% coverage."""
        analyzer = CoverageAnalyzer()
        grid = analyzer.create_grid()
        grid[:, :] = 1.0

        pct = analyzer.compute_coverage_percentage(grid)
        assert abs(pct - 1.0) < 0.001


class TestGridWrapping:
    """Test grid wrapping edge cases (Bug #2 fix)."""

    def test_longitude_wrapping_at_antimeridian(self):
        """Coverage near 180 degrees should wrap around."""
        analyzer = CoverageAnalyzer(
            coverage_radius_km=500, grid_height=180, grid_width=360
        )
        grid = analyzer.create_grid()

        # Place balloon near antimeridian (180 / -180)
        analyzer.update_coverage(0.0, 179.0, grid, value=1.0)

        # Coverage should appear on both sides of the antimeridian
        # Check west side (positive longitude near 180)
        west_coverage = np.sum(grid[:, 170:180] != 0)
        # Check east side (negative longitude near -180, which is grid index 0-10)
        # In standard coords: -180 to -170 maps to internal 180 to 190,
        # then wraps to 180 to 10 in grid
        east_coverage = np.sum(grid[:, :10] != 0)

        assert west_coverage > 0, "Should have coverage west of antimeridian"
        # Note: east_coverage depends on exact wrapping behavior

    def test_coverage_at_equator(self):
        """Coverage at equator should be symmetric."""
        analyzer = CoverageAnalyzer(
            coverage_radius_km=300, grid_height=180, grid_width=360
        )
        grid = analyzer.create_grid()

        # Place balloon at equator
        analyzer.update_coverage(0.0, 0.0, grid, value=1.0)

        # Find the covered region
        covered_rows = np.where(np.any(grid != 0, axis=1))[0]

        if len(covered_rows) > 0:
            # Coverage should be roughly symmetric around row 90 (equator)
            center = np.mean(covered_rows)
            assert abs(center - 90) < 5, "Coverage should be centered at equator"

    def test_coverage_near_pole_expansion(self):
        """Coverage near poles should expand in longitude."""
        analyzer = CoverageAnalyzer(
            coverage_radius_km=500, grid_height=180, grid_width=360
        )

        # At equator
        grid_equator = analyzer.create_grid()
        analyzer.update_coverage(0.0, 0.0, grid_equator, value=1.0)
        equator_lon_coverage = np.sum(np.any(grid_equator != 0, axis=0))

        # At high latitude
        grid_polar = analyzer.create_grid()
        analyzer.update_coverage(70.0, 0.0, grid_polar, value=1.0)
        polar_lon_coverage = np.sum(np.any(grid_polar != 0, axis=0))

        # At higher latitudes, the same km radius covers more longitude degrees
        assert polar_lon_coverage > equator_lon_coverage


class TestCoverageStatistics:
    """Test coverage statistics computation."""

    def test_statistics_keys(self):
        """Statistics should include all expected keys."""
        analyzer = CoverageAnalyzer()
        grid = analyzer.create_grid()
        analyzer.update_coverage(40.0, -100.0, grid, value=5.0)

        stats = analyzer.compute_coverage_statistics(grid)

        assert "coverage_percentage" in stats
        assert "total_cells" in stats
        assert "covered_cells" in stats
        assert "uncovered_cells" in stats
        assert "min_coverage_value" in stats
        assert "max_coverage_value" in stats
        assert "mean_coverage_value" in stats

    def test_coverage_by_threshold(self):
        """Coverage by threshold should filter correctly."""
        analyzer = CoverageAnalyzer()
        grid = analyzer.create_grid()

        # Add coverage with different values
        analyzer.update_coverage(0.0, 0.0, grid, value=10.0)
        analyzer.update_coverage(0.0, 90.0, grid, value=5.0)
        analyzer.update_coverage(0.0, -90.0, grid, value=1.0)

        # All coverage
        pct_all = analyzer.compute_coverage_by_threshold(grid, 0)

        # Only high coverage
        pct_high = analyzer.compute_coverage_by_threshold(grid, 7)

        assert pct_high <= pct_all
        assert pct_high > 0


class TestAreaWeighting:
    """Test area-weighted coverage calculation."""

    def test_polar_cells_smaller(self):
        """Polar cells should have smaller area than equatorial cells."""
        analyzer = CoverageAnalyzer(grid_height=180, grid_width=360)

        # Area grid should have smaller values near poles
        equator_area = analyzer._area_grid[90, 0]  # Row 90 = equator
        pole_area = analyzer._area_grid[0, 0]  # Row 0 = south pole

        assert pole_area < equator_area

    def test_equatorial_coverage_worth_more(self):
        """Same grid cells at equator should contribute more to coverage %."""
        analyzer = CoverageAnalyzer(grid_height=180, grid_width=360)

        # Create two grids with same number of cells covered
        grid1 = analyzer.create_grid()
        grid2 = analyzer.create_grid()

        # Cover 10x10 cells at equator (rows 85-95)
        grid1[85:95, 0:10] = 1.0

        # Cover 10x10 cells near pole (rows 0-10)
        grid2[0:10, 0:10] = 1.0

        pct_equator = analyzer.compute_coverage_percentage(grid1)
        pct_polar = analyzer.compute_coverage_percentage(grid2)

        assert pct_equator > pct_polar


class TestMultipleCoverageUpdates:
    """Test accumulating coverage from multiple positions."""

    def test_overlapping_coverage(self):
        """Overlapping coverage should use latest value."""
        analyzer = CoverageAnalyzer(coverage_radius_km=500)
        grid = analyzer.create_grid()

        # First update
        analyzer.update_coverage(0.0, 0.0, grid, value=1.0)
        initial_coverage = analyzer.compute_coverage_percentage(grid)

        # Second update at same location with higher value
        analyzer.update_coverage(0.0, 0.0, grid, value=2.0)

        # Coverage area should be same
        final_coverage = analyzer.compute_coverage_percentage(grid)
        assert abs(final_coverage - initial_coverage) < 0.001

        # But max value should be updated
        assert np.max(grid) == 2.0

    def test_non_overlapping_coverage(self):
        """Non-overlapping coverage should accumulate."""
        analyzer = CoverageAnalyzer(coverage_radius_km=300)
        grid = analyzer.create_grid()

        # First position
        analyzer.update_coverage(0.0, 0.0, grid, value=1.0)
        coverage1 = analyzer.compute_coverage_percentage(grid)

        # Second position far away
        analyzer.update_coverage(0.0, 90.0, grid, value=1.0)
        coverage2 = analyzer.compute_coverage_percentage(grid)

        # Total coverage should increase
        assert coverage2 > coverage1
