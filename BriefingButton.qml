import QtQuick
import QtQuick.Controls as Controls
import qs.Commons

Controls.Button {
    id: control
    property color ink: Color.foreground
    property color accent: Color.accent
    implicitHeight: Style.space(42)
    contentItem: Text {
        text: control.text
        color: control.ink
        font.family: Style.font.family
        font.pixelSize: Style.font.body
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
    background: Rectangle {
        radius: Style.space(6)
        color: control.down ? Qt.rgba(control.ink.r, control.ink.g, control.ink.b, 0.18) : "transparent"
        border.width: control.activeFocus ? 2 : 1
        border.color: control.activeFocus ? control.accent : Qt.rgba(control.ink.r, control.ink.g, control.ink.b, 0.3)
    }
}
