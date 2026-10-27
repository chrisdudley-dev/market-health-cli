package dev.chrisdudley.markethealth

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class NavigationTest {
    @get:Rule val rule = createAndroidComposeRule<MainActivity>()

    @Test fun allEightNativeDestinationsOpen() {
        for (name in listOf("Portfolio", "Trading List", "Buy Candidates", "Market Health", "History", "Policy", "Settings", "Dashboard")) {
            rule.onNodeWithText("Menu").performClick()
            rule.onNode(hasText(name) and hasClickAction()).performClick()
            rule.onNode(hasText(name) and !hasClickAction()).assertIsDisplayed()
        }
    }

    @Test fun manualHoldingCanBeSavedAndRemoved() {
        rule.onNodeWithText("Menu").performClick()
        rule.onNode(hasText("Portfolio") and hasClickAction()).performClick()
        rule.onNodeWithText("+ Owned").performClick()
        rule.onNodeWithText("Symbol").performTextInput("IVE")
        rule.onNodeWithText("Shares").performTextInput("3")
        rule.onNodeWithText("Save Owned").performClick()
        rule.waitUntil(30_000) { rule.onAllNodesWithText("IVE").fetchSemanticsNodes().isNotEmpty() }
        rule.onNodeWithText("IVE").assertIsDisplayed()
        rule.onNodeWithText("Remove").performClick()
        rule.waitUntil(30_000) { rule.onAllNodesWithText("IVE").fetchSemanticsNodes().isEmpty() }
    }
}
