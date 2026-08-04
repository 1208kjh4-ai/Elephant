# -*- coding: utf-8 -*-
import Rhino.UI


def main():
    shortcut_list = [
        "Elephant Tools command guide",
        "--------------------------------------------------",
        "Door and opening tools",
        " Swing         : Swing door generator",
        " Sliding       : Sliding door generator",
        " Folding       : Folding door generator",
        " Spinning      : Spinning door generator",
        " Curtainwall   : Curtain wall generator",
        "--------------------------------------------------",
        "Stair, elevator, and structure tools",
        " Stair         : Stair generator",
        " CoreStair     : Core stair generator",
        " CustomStair   : Custom stair generator",
        " Escalator     : Escalator generator",
        " Elevator      : Elevator generator",
        " Auditorium    : Auditorium section generator",
        " SpiralStair   : Spiral stair generator",
        " Handrail      : Handrail generator",
        " Truss         : Truss generator",
        " SpaceTruss    : Space truss generator",
        " 3DTruss       : 3D truss generator",
        " Hbeam         : H-beam generator",
        "--------------------------------------------------",
        "Road and marking tools",
        " Arrow         : Road arrow marking generator",
        " Cross         : Crosswalk generator",
        " Lane          : Lane marking generator",
        "--------------------------------------------------",
        "Terrain and SHP tools",
        " SHP           : Import SHP file",
        " CreateContour : Import terrain / road contour curves",
        " ApplyRoad     : Apply road curves to terrain",
        " Building      : Generate buildings from SHP data",
        " Drop2Srf      : Drop objects to surface",
        "--------------------------------------------------",
        "Utility tools",
        " Parapet       : Parapet generator",
        " Tree          : Tree array tool",
        " MZ            : Match Z-height",
        " AA            : Array between two points",
        " CHP           : Chamfer polyline tool",
        " AZ            : Adjust object Z height",
        " ShowShortCuts : Show this command guide",
        "--------------------------------------------------",
        "Type a command name in the Rhino command line and press Enter.",
    ]

    Rhino.UI.Dialogs.ShowTextDialog(
        "\n".join(shortcut_list),
        "Elephant Tools command list",
    )


if __name__ == "__main__":
    main()
