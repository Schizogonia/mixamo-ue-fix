import traceback
import sys
import os
import bpy
from bpy_extras import anim_utils


def clean_scene():
    """Remove all objects from the scene (camera, cube, light, etc.)"""
    print("[Step 1] Cleaning scene...")
    
    # Exit any mode to Object Mode
    if bpy.context.active_object and bpy.context.active_object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    
    # Select and delete all objects
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    
    # Remove orphaned data blocks
    for block in bpy.data.meshes:
        bpy.data.meshes.remove(block)
    for block in bpy.data.armatures:
        bpy.data.armatures.remove(block)
    for block in bpy.data.actions:
        bpy.data.actions.remove(block)


def import_fbx(filepath):
    """Import FBX animation with specified settings."""
    print(f"[Step 2] Importing FBX: {filepath}")
    
    bpy.ops.import_scene.fbx(
        filepath=filepath,
        # General
        # global_scale=1.0,
        use_custom_props=True,
        use_custom_props_enum_as_string=True,
        # Geometry
        use_image_search=True,
        use_custom_normals=True,
        colors_type='SRGB',
        # Animation
        use_anim=True,
        anim_offset=1.0,
        ignore_leaf_bones=False,
        automatic_bone_orientation=False,
        force_connect_children=False,
        
        use_subsurf=False,
    )


def fix_bones(armature_obj):
    """
    Transfer XY movement from Hips to the Armature object itself (root).
    Hips keeps only Z movement.
    """
    print("[Step 3] Collecting Hips animation...")
    bpy.context.view_layer.objects.active = armature_obj
    
    # Enter Pose mode to read Hips animation
    bpy.ops.object.mode_set(mode='POSE')
    
    # Find Hips pose bone
    hips_pose = None
    hips_name = None
    for pbone in armature_obj.pose.bones:
        if "hips" in pbone.name.lower():
            hips_pose = pbone
            hips_name = pbone.name
            break
    
    if not hips_pose:
        print("[Warning] Hips bone not found, skipping")
        bpy.ops.object.mode_set(mode='OBJECT')
        return
    
    print(f"[Step 4] Found Hips bone: {hips_name}")
    
    # Get frame range
    frame_start = int(bpy.context.scene.frame_start)
    frame_end = int(bpy.context.scene.frame_end)
    
    if armature_obj.animation_data and armature_obj.animation_data.action:
        action = armature_obj.animation_data.action
        frame_start = int(action.frame_range[0])
        frame_end = int(action.frame_range[1])
        print(f"        Action: {action.name}, frames {frame_start}-{frame_end}")
    
    # Collect WORLD positions of Hips for each frame (before any modifications)
    print("[Step 5] Collecting Hips world positions...")
    hips_world_data = {}
    
    for frame in range(frame_start, frame_end + 1):
        bpy.context.scene.frame_set(frame)
        # Get world position of Hips bone head
        world_matrix = armature_obj.matrix_world @ hips_pose.matrix
        world_pos = world_matrix.translation.copy()
        hips_world_data[frame] = world_pos
    
    # Get the starting position (first frame) as reference
    start_pos = hips_world_data[frame_start]
    print(f"        Collected {len(hips_world_data)} frames")
    print(f"        Start position (frame {frame_start}): X={start_pos.x:.3f}, Y={start_pos.y:.3f}, Z={start_pos.z:.3f}")
    
    # Calculate the base height (Z on first frame) - this is "floor level" for Hips
    base_z = start_pos.z
    
    # Now apply animation:
    # - Armature object gets XY delta from first frame (horizontal movement)
    # - Hips gets Z delta from first frame (vertical movement) - NO change to original animation
    print("[Step 6] Applying keyframes to Armature object only...")
    
    bpy.ops.object.mode_set(mode='OBJECT')
    
    for frame in range(frame_start, frame_end + 1):
        bpy.context.scene.frame_set(frame)
        
        world_pos = hips_world_data[frame]
        
        # Armature object moves on XY plane relative to start position
        # Z stays at 0 (floor)
        armature_obj.location.x = world_pos.x - start_pos.x
        armature_obj.location.y = world_pos.y - start_pos.y
        armature_obj.location.z = 0
        armature_obj.keyframe_insert(data_path="location", frame=frame)
    
    print(f"        Applied {frame_end - frame_start + 1} frames to Armature")
    
    # Now we need to remove XY movement from Hips bone
    # by adjusting its local location
    print("[Step 7] Removing XY from Hips bone animation...")
    
    bpy.ops.object.mode_set(mode='POSE')
    hips_pose = armature_obj.pose.bones.get(hips_name)
    
    # Get the bone's rest matrix to convert world to local
    hips_bone = armature_obj.data.bones.get(hips_name)
    
    for frame in range(frame_start, frame_end + 1):
        bpy.context.scene.frame_set(frame)
        
        # We need to zero out XY in local bone space
        # Just set X and Z to 0 (in bone local: X=side, Y=up, Z=forward for upward-pointing bones)
        # Keep original Y (vertical in bone space)
        original_y = hips_pose.location.y
        hips_pose.location.x = 0
        hips_pose.location.y = original_y  # Keep vertical
        hips_pose.location.z = 0
        hips_pose.keyframe_insert(data_path="location", frame=frame)
    
    print(f"        Adjusted Hips for {frame_end - frame_start + 1} frames")
    
    # Return to Object Mode
    bpy.ops.object.mode_set(mode='OBJECT')


def fix_bones_quinn(armature_obj):
    """
    Fix Quinn/Manny (UE Skeleton) using Blender 5.0 ready workflow.
    Uses anim_utils for proper channelbag handling.
    """
    # Step 1: Setup original
    original = armature_obj
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = original
    original.select_set(True)
    
    original_action = original.animation_data.action if original.animation_data else None
    if not original_action:
        print("[Error] No animation data found!")
        return
    
    # Step 1: Duplicate
    bpy.ops.object.duplicate()
    duplicate = bpy.context.active_object
    duplicate.name = f"{original.name}.001"
    print(f"[Step 3] Created duplicate: {duplicate.name}")
    
    # Store references to junk data for cleanup
    junk_action = None
    if duplicate.animation_data and duplicate.animation_data.action:
        junk_action = duplicate.animation_data.action
    junk_data = duplicate.data
    
    # Return to original
    bpy.ops.object.select_all(action='DESELECT')
    original.select_set(True)
    bpy.context.view_layer.objects.active = original
    
    obj = bpy.context.object
    action = obj.animation_data.action
    slot = obj.animation_data.action_slot
    
    channelbag = anim_utils.action_get_channelbag_for_slot(action, slot)
    
    # Step 2: Remove object fcurves (not bone fcurves)
    fcurves_to_remove = []
    for fcurve in channelbag.fcurves:
        if "pose.bones" not in fcurve.data_path:
            fcurves_to_remove.append(fcurve)
    
    count = 0
    for fcurve in fcurves_to_remove:
        channelbag.fcurves.remove(fcurve)
        count += 1
    
    print(f"[Step 4] Removed {count} object animation curves.")
    
    # Reset transforms
    original.location = (0, 0, 0)
    original.rotation_euler = (0, 0, 0)
    original.scale = (1, 1, 1)
    
    # Step 3: Create Empty with constraints
    bpy.ops.object.empty_add(type='PLAIN_AXES')
    empty_obj = bpy.context.active_object
    empty_obj.name = "Target_Empty"
    print("[Step 5] Created Empty.")
    
    c_loc = empty_obj.constraints.new('COPY_LOCATION')
    c_loc.target = duplicate
    c_loc.subtarget = "pelvis"
    c_loc.use_x = True
    c_loc.use_y = True
    c_loc.use_z = False
    
    c_scale = empty_obj.constraints.new('COPY_SCALE')
    c_scale.target = duplicate
    c_scale.subtarget = "pelvis"
    c_scale.use_x = True
    c_scale.use_y = True
    c_scale.use_z = True
    print("[Debug] Empty constraints configured.")
    
    # Step 4: Setup bone constraints
    bpy.ops.object.select_all(action='DESELECT')
    original.select_set(True)
    bpy.context.view_layer.objects.active = original
    bpy.ops.object.mode_set(mode='POSE')
    
    pbone_root = original.pose.bones["root"]
    c_trans_root = pbone_root.constraints.new('COPY_TRANSFORMS')
    c_trans_root.target = empty_obj
    print("[Step 6] Root linked to Empty.")
    
    for child_bone in pbone_root.children:
        c_trans = child_bone.constraints.new('COPY_TRANSFORMS')
        c_trans.target = duplicate
        c_trans.subtarget = child_bone.name
        print(f"[Debug] Child '{child_bone.name}' linked to duplicate.")
    
    # Step 5: Select bones and bake (Blender 5.0: use PoseBone.select)
    pbone_root.select = True
    for child_bone in pbone_root.children:
        child_bone.select = True
    
    start_frame = int(action.frame_range[0])
    end_frame = int(action.frame_range[1])
    
    print("[Step 7] Baking animation...")
    bpy.ops.nla.bake(
        frame_start=start_frame,
        frame_end=end_frame,
        only_selected=True,
        visual_keying=True,
        clear_constraints=True,
        use_current_action=True,
        bake_types={'POSE'}
    )
    print("[Debug] Baking complete.")
    
    # Cleanup
    bpy.ops.object.mode_set(mode='OBJECT')
    
    bpy.data.objects.remove(duplicate, do_unlink=True)
    bpy.data.objects.remove(empty_obj, do_unlink=True)
    
    if junk_action:
        print(f"[Debug] Removing junk action: {junk_action.name}")
        bpy.data.actions.remove(junk_action)
    
    if junk_data and junk_data != original.data:
        try:
            bpy.data.armatures.remove(junk_data)
            print("[Debug] Removed duplicate armature data.")
        except ReferenceError:
            pass  # Already removed
    
    print("[Step 8] Cleanup complete.")


def rename_top_object():
    """Rename the top-level object (no parent) to 'root'."""
    print("[Step 7] Renaming top-level object to 'root'...")
    
    # Find object without parent (top-level in hierarchy)
    top_object = None
    for obj in bpy.context.scene.objects:
        if obj.parent is None:
            top_object = obj
            break
    
    if top_object:
        original_name = top_object.name
        top_object.name = "root"
        print(f"        Renamed: '{original_name}' -> 'root'")
        return top_object
    else:
        print("[Warning] No top-level object found")
        return None


def select_hierarchy(obj):
    """Select the specified object and all its children (mesh, armature, etc.)."""
    print("[Step 9] Selecting object and all children...")
    bpy.ops.object.select_all(action='DESELECT')
    
    # Select the object itself
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    
    # Recursively select all children
    def select_children(parent):
        for child in parent.children:
            child.select_set(True)
            select_children(child)
    
    select_children(obj)
    
    # Log selected objects
    selected = [o.name for o in bpy.context.selected_objects]
    print(f"        Selected {len(selected)} objects: {selected}")


def export_fbx(output_path):
    """Export selected objects to FBX with specified settings."""
    print(f"[Step 10] Exporting FBX to: {output_path}")
    
    bpy.ops.export_scene.fbx(
        filepath=output_path,
        # Include
        use_selection=False,  # Limit to Selected Objects
        object_types={'EMPTY', 'CAMERA', 'LIGHT', 'ARMATURE', 'MESH', 'OTHER'},
        use_custom_props=False,
        # Transform
        global_scale=1.0,
        apply_scale_options='FBX_SCALE_ALL',  # All Local
        axis_forward='-Z',
        axis_up='Y',
        apply_unit_scale=True,
        use_space_transform=True,
        bake_space_transform=False,
        # Geometry
        mesh_smooth_type='FACE',  # Normals Only
        use_subsurf=False,
        use_mesh_modifiers=True,  # Apply Modifiers
        use_mesh_edges=False,
        use_triangles=False,
        use_tspace=False,
        colors_type='SRGB',
        prioritize_active_color=False,
        # Armature
        primary_bone_axis='Y',
        secondary_bone_axis='X',
        armature_nodetype='NULL',
        use_armature_deform_only=False,
        add_leaf_bones=True,  # IMPORTANT: disabled!
        # Animation
        bake_anim=True,
        bake_anim_use_all_bones=True,  # Key All Bones
        bake_anim_use_nla_strips=True,  # NLA Strips
        bake_anim_use_all_actions=True,  # All Actions
        bake_anim_force_startend_keying=True,  # Force Start/End Keying
        bake_anim_step=1.0,  # Sampling Rate
        bake_anim_simplify_factor=1.0,  # Simplify
    )


def main():
    """Main function for processing FBX files."""
    argv = sys.argv
    
    try:
        # Parse command line arguments after "--"
        if "--" in argv:
            args = argv[argv.index("--") + 1:]
        else:
            args = []
        
        if len(args) < 2:
            print("[Error] Not enough arguments. Usage: blender ... -- input.fbx output_dir [mode]")
            return

        input_fbx = args[0]
        output_dir = args[1]
        mode = args[2] if len(args) > 2 else "mixamo"  # Default mode is mixamo
        
        print(f"[Info] Processing mode: {mode}")
        print(f"[Info] All args: {args}")

        # Clean scene
        clean_scene()
        
        # Import FBX
        import_fbx(input_fbx)
        
        # Find armature
        armature = None
        for obj in bpy.context.scene.objects:
            if obj.type == 'ARMATURE':
                armature = obj
                break
        
        if armature:
            if mode == "ue5_skm":
                # Quinn skeleton: has internal root bone to remove
                fix_bones_quinn(armature)
                # For Quinn: skip rename/select, go directly to export
            else:
                # Standard Mixamo: no internal root, transfer Hips XY to armature
                fix_bones(armature)
                
                # Rename top-level object (Mixamo only)
                root_obj = rename_top_object()
                
                if root_obj:
                    # Select the root object and all children (mesh + armature)
                    select_hierarchy(root_obj)
        
        # Build output path and export
        filename = os.path.basename(input_fbx)
        out_name = f"{os.path.splitext(filename)[0]}_Fixed.fbx"
        target_path = os.path.join(output_dir, out_name)
        
        export_fbx(target_path)
        
        print("[Success] All steps completed!")

    except Exception as e:
        print(f"[Error] {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()