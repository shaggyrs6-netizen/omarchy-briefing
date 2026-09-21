import QtQuick
import qs.Commons
import qs.Ui

BarWidget {
    id: root
    moduleName: "shaggyrs6.briefing"
    readonly property bool opened: panelLoader.item ? panelLoader.item.opened : false
    readonly property bool popoutSwitchClosing: panelLoader.item ? panelLoader.item.popoutSwitchClosing : false
    function open() { if (panelLoader.item) panelLoader.item.open() }
    function close() { if (panelLoader.item) panelLoader.item.close() }
    function closeForPopoutSwitch() { if (panelLoader.item) panelLoader.item.closeForPopoutSwitch() }
    function injectPanel() {
        if (!panelLoader.item) return
        panelLoader.item.bar = root.bar
        panelLoader.item.anchorItem = button
        panelLoader.item.hostWidget = root
    }
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight
    onBarChanged: injectPanel()
    Loader {
        id: panelLoader
        active: true
        source: Qt.resolvedUrl("Panel.qml")
        visible: false
        onLoaded: { root.injectPanel(); Qt.callLater(root.injectPanel) }
    }
    BarIconButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        readonly property int unreadCount: panelLoader.item ? (panelLoader.item.briefingData.unread || 0) : 0
        tooltipText: "Omarchy Briefing — updates explained & news" + (unreadCount ? " · " + unreadCount + " unread" : "")
        // A small newspaper drawn with native shapes: follows the bar colour,
        // stays sharp at any scale and does not depend on an icon-font glyph.
        iconComponent: Component {
            Item {
                id: newspaper
                readonly property real unit: Math.min(width, height) / 24
                readonly property color ink: button.foreground
                Rectangle {
                    x: 2 * newspaper.unit; y: 6 * newspaper.unit
                    width: 5 * newspaper.unit; height: 15 * newspaper.unit
                    radius: newspaper.unit
                    color: "transparent"
                    border.color: newspaper.ink
                    border.width: Math.max(1, 1.5 * newspaper.unit)
                }
                Rectangle {
                    x: 6 * newspaper.unit; y: 3 * newspaper.unit
                    width: 16 * newspaper.unit; height: 18 * newspaper.unit
                    radius: newspaper.unit
                    color: "transparent"
                    border.color: newspaper.ink
                    border.width: Math.max(1, 1.5 * newspaper.unit)
                }
                Rectangle { x: 9 * newspaper.unit; y: 6 * newspaper.unit; width: 10 * newspaper.unit; height: 2 * newspaper.unit; color: newspaper.ink }
                Rectangle { x: 9 * newspaper.unit; y: 10 * newspaper.unit; width: 4 * newspaper.unit; height: 4 * newspaper.unit; color: newspaper.ink }
                Rectangle { x: 15 * newspaper.unit; y: 10 * newspaper.unit; width: 4 * newspaper.unit; height: newspaper.unit; color: newspaper.ink }
                Rectangle { x: 15 * newspaper.unit; y: 13 * newspaper.unit; width: 4 * newspaper.unit; height: newspaper.unit; color: newspaper.ink }
                Rectangle { x: 9 * newspaper.unit; y: 17 * newspaper.unit; width: 10 * newspaper.unit; height: newspaper.unit; color: newspaper.ink }
                Rectangle {
                    visible: button.unreadCount > 0
                    x: 19 * newspaper.unit; y: 0
                    width: 5 * newspaper.unit; height: width; radius: width / 2
                    color: Color.accent
                }
            }
        }
        onPressed: function(b) {
            if (b === Qt.LeftButton && panelLoader.item) {
                if (root.opened) root.close(); else root.open()
            }
        }
    }
}
